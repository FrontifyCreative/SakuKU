from datetime import date, timedelta
from functools import wraps
from urllib.parse import urlparse
import csv
import hmac
import io
import math
import os
import re
import secrets
import sqlite3
import time
import json
import urllib.parse
import urllib.request
from flask import Flask, Response, g, render_template, request, jsonify, session, redirect, url_for
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "sakuku.db")
IS_PROD = os.environ.get("SAKUKU_ENV", "").lower() == "production"


def load_secret_key():
    """Secret key acak per instalasi. Tidak pernah memakai nilai bawaan yang tertulis di kode."""
    env_key = os.environ.get("SECRET_KEY", "")
    if len(env_key) >= 32:
        return env_key
    path = os.path.join(BASE_DIR, ".secret_key")
    if os.path.exists(path):
        with open(path, "r") as fh:
            key = fh.read().strip()
        if len(key) >= 32:
            return key
    key = secrets.token_hex(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(key)
    return key


app = Flask(__name__)
app.secret_key = load_secret_key()
app.config.update(
    SESSION_COOKIE_NAME="sakuku_session",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=IS_PROD,
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
    MAX_CONTENT_LENGTH=64 * 1024,
)
if os.environ.get("TRUST_PROXY") == "1":
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# Kebijakan keamanan
ADMIN_IDLE_SECONDS = 20 * 60        # operator otomatis keluar jika diam 20 menit
ADMIN_MAX_SECONDS = 8 * 60 * 60     # dan paling lama 8 jam per sesi
LOGIN_WINDOW = 15 * 60
LOGIN_MAX_PER_PAIR = 5              # per kombinasi username + IP
LOGIN_MAX_PER_IP = 30               # semprot banyak username dari satu IP
REGISTER_MAX_PER_HOUR = 5
REAUTH_MAX = 5
USERNAME_RE = re.compile(r"^[a-z0-9_]{3,30}$")
# Satu sumber kebenaran kategori: dikirim ke halaman dan dipakai untuk validasi di server.
CATEGORIES = {
    "keluar": ["Makan & Minum", "Transport", "Kuota & Internet", "Kebutuhan Sekolah", "Hiburan", "Tabungan", "Lainnya"],
    "masuk": ["Uang Saku", "Penghasilan Tambahan", "Lainnya"],
}
COMMON_PASSWORDS = {
    "password", "password1", "password123", "12345678", "123456789", "1234567890", "qwerty123",
    "qwertyui", "admin123", "admin1234", "abcd1234", "abc12345", "iloveyou1", "sakuku123", "11111111",
}
# Anti-robot: Cloudflare Turnstile. Aktif hanya jika KEDUA kunci diisi lewat environment variable.
TURNSTILE_SITE_KEY = os.environ.get("TURNSTILE_SITE_KEY", "").strip()
TURNSTILE_SECRET_KEY = os.environ.get("TURNSTILE_SECRET_KEY", "").strip()
TURNSTILE_ENABLED = bool(TURNSTILE_SITE_KEY and TURNSTILE_SECRET_KEY)
TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
CAPTCHA_MAX_PER_IP = 20  # batas verifikasi gagal/kosong per IP per 15 menit (menghemat panggilan ke Cloudflare)


def build_csp():
    cf = " https://challenges.cloudflare.com" if TURNSTILE_ENABLED else ""
    return "; ".join([
        "default-src 'self'",
        f"script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com https://unpkg.com https://cdn.jsdelivr.net{cf}",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "font-src https://fonts.gstatic.com",
        "img-src 'self' data:",
        f"connect-src 'self'{cf}",
        f"frame-src{cf}" if cf else "frame-src 'none'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ])


CSP = build_csp()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def seed_default_templates(cur, user_id):
    defaults = [
        ("Parkir", "keluar", 2000, "Transport"),
        ("Jajan Kantin", "keluar", 12000, "Makan & Minum"),
        ("Uang Kas", "keluar", 5000, "Kebutuhan Sekolah"),
    ]
    cur.executemany(
        "INSERT INTO quick_templates (user_id, nama, tipe, nominal, kategori) VALUES (?, ?, ?, ?, ?)",
        [(user_id, n, t, nom, k) for n, t, nom, k in defaults],
    )


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nama TEXT NOT NULL,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('user', 'admin')),
            is_active INTEGER NOT NULL DEFAULT 1,
            daily_limit INTEGER NOT NULL DEFAULT 30000,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            tipe TEXT NOT NULL CHECK(tipe IN ('masuk', 'keluar')),
            nominal INTEGER NOT NULL CHECK(nominal > 0),
            kategori TEXT NOT NULL,
            tanggal TEXT NOT NULL,
            catatan TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS savings_goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            nama TEXT NOT NULL,
            target INTEGER NOT NULL CHECK(target > 0),
            terkumpul INTEGER NOT NULL DEFAULT 0 CHECK(terkumpul >= 0),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS debts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            tipe TEXT NOT NULL CHECK(tipe IN ('hutang', 'piutang')),
            nama_orang TEXT NOT NULL,
            nominal INTEGER NOT NULL CHECK(nominal > 0),
            catatan TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'belum' CHECK(status IN ('belum', 'lunas')),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS quick_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            nama TEXT NOT NULL,
            tipe TEXT NOT NULL CHECK(tipe IN ('masuk', 'keluar')),
            nominal INTEGER NOT NULL CHECK(nominal > 0),
            kategori TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT ''
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT NOT NULL,
            aksi TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute(
        "INSERT OR IGNORE INTO app_settings (key, value) VALUES ('announcement', '')"
    )

    cur.execute("""
        CREATE TABLE IF NOT EXISTS auth_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scope TEXT NOT NULL,
            ident TEXT NOT NULL,
            ts REAL NOT NULL
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_auth_attempts ON auth_attempts (scope, ident, ts)")

    # Migrasi aman untuk database lama (v3/v4)
    cols = {r["name"] for r in cur.execute("PRAGMA table_info(users)").fetchall()}
    if "must_change_password" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN must_change_password INTEGER NOT NULL DEFAULT 0")
    if "session_version" not in cols:
        cur.execute("ALTER TABLE users ADD COLUMN session_version INTEGER NOT NULL DEFAULT 0")

    admin_exists = cur.execute("SELECT id FROM users WHERE role = 'admin'").fetchone()
    if not admin_exists:
        env_pw = os.environ.get("ADMIN_PASSWORD", "")
        initial_pw = env_pw if env_pw and not validate_password(env_pw, "admin") else random_password(14)
        generated = initial_pw != env_pw
        cur.execute(
            "INSERT OR IGNORE INTO users (nama, username, password_hash, role, must_change_password) "
            "VALUES (?, ?, ?, 'admin', ?)",
            ("Operator", "admin", generate_password_hash(initial_pw), 1 if generated else 0),
        )
        admin_id = cur.lastrowid
        if admin_id:
            seed_default_templates(cur, admin_id)
        if generated:
            print("\n" + "=" * 62)
            print("  AKUN OPERATOR DIBUAT (hanya ditampilkan SEKALI)")
            print(f"  Username : admin")
            print(f"  Password : {initial_pw}")
            print("  Anda akan diminta mengganti password saat login pertama.")
            print("=" * 62 + "\n")

    # Database lama yang masih memakai admin/admin123 wajib ganti password
    legacy = cur.execute("SELECT id, password_hash FROM users WHERE username = 'admin' AND role = 'admin'").fetchone()
    if legacy and check_password_hash(legacy["password_hash"], "admin123"):
        cur.execute("UPDATE users SET must_change_password = 1 WHERE id = ?", (legacy["id"],))
        print("\n[PERINGATAN] Akun admin masih memakai password bawaan 'admin123'. "
              "Password akan dipaksa diganti saat login berikutnya.\n")

    conn.commit()
    conn.close()


def log_activity(user_id, username, aksi):
    conn = get_db()
    conn.execute(
        "INSERT INTO activity_logs (user_id, username, aksi) VALUES (?, ?, ?)",
        (user_id, username or "-", aksi),
    )
    conn.commit()
    conn.close()


# ---------- Util keamanan ----------
PASSWORD_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
DUMMY_HASH = generate_password_hash(secrets.token_hex(8))  # menyamakan waktu respons login
MAX_NOMINAL = 10_000_000_000


def random_password(n=12):
    while True:
        pw = "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(n))
        if re.search(r"\d", pw) and re.search(r"[A-Za-z]", pw):
            return pw


def validate_password(pw, username="", nama=""):
    """Mengembalikan pesan error (str) atau None jika password memenuhi syarat."""
    if len(pw) < 8:
        return "Password minimal 8 karakter"
    if len(pw) > 128:
        return "Password terlalu panjang (maks. 128 karakter)"
    if not (re.search(r"[A-Za-z]", pw) and re.search(r"\d", pw)):
        return "Password harus mengandung huruf dan angka"
    low = pw.lower()
    if low in COMMON_PASSWORDS or len(set(low)) < 4:
        return "Password terlalu mudah ditebak, pilih yang lebih unik"
    if username and (low == username.lower() or username.lower() in low and len(username) >= 4):
        return "Password tidak boleh mengandung username"
    return None


def txt(v, n=200):
    """Bersihkan teks bebas: buang karakter kontrol dan batasi panjang."""
    return re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", str(v if v is not None else "")).strip()[:n]


def to_int(v):
    """Angka bulat positif dalam batas wajar, selain itu 0 (ditolak oleh validasi pemanggil)."""
    try:
        n = int(v)
    except (TypeError, ValueError, OverflowError):
        return 0
    return n if 0 < n <= MAX_NOMINAL else 0


def category_ok(tipe, kategori):
    return kategori in CATEGORIES.get(tipe, ())


def safe_date(v):
    try:
        d = date.fromisoformat(str(v or "").strip()[:10])
    except ValueError:
        return None
    return d.isoformat() if 2000 <= d.year <= 2100 else None


def csv_safe(v):
    """Cegah CSV/formula injection saat file dibuka di Excel/Sheets."""
    v = "" if v is None else str(v)
    return "'" + v if v[:1] in ("=", "+", "-", "@", "\t", "\r") else v


def client_ip():
    return request.remote_addr or "unknown"


def attempts_count(scope, ident, window):
    conn = get_db()
    n = conn.execute(
        "SELECT COUNT(*) FROM auth_attempts WHERE scope = ? AND ident = ? AND ts > ?",
        (scope, ident, time.time() - window),
    ).fetchone()[0]
    conn.close()
    return n


def attempts_record(scope, ident):
    conn = get_db()
    conn.execute("INSERT INTO auth_attempts (scope, ident, ts) VALUES (?, ?, ?)", (scope, ident, time.time()))
    conn.execute("DELETE FROM auth_attempts WHERE ts < ?", (time.time() - 86400,))
    conn.commit()
    conn.close()


def attempts_clear(scope, ident):
    conn = get_db()
    conn.execute("DELETE FROM auth_attempts WHERE scope = ? AND ident = ?", (scope, ident))
    conn.commit()
    conn.close()


def retry_minutes(scope, ident, window):
    conn = get_db()
    row = conn.execute(
        "SELECT MIN(ts) FROM auth_attempts WHERE scope = ? AND ident = ? AND ts > ?",
        (scope, ident, time.time() - window),
    ).fetchone()
    conn.close()
    oldest = row[0] if row and row[0] else time.time()
    return max(1, math.ceil((oldest + window - time.time()) / 60))


def too_many(minutes):
    resp = jsonify({"error": f"Terlalu banyak percobaan. Coba lagi dalam {minutes} menit."})
    resp.status_code = 429
    resp.headers["Retry-After"] = str(minutes * 60)
    return resp


# ---------- Anti-robot (Cloudflare Turnstile) ----------
def _siteverify(token, ip):
    """Tanya Cloudflare apakah token valid. Dipisah agar mudah diuji."""
    body = urllib.parse.urlencode(
        {"secret": TURNSTILE_SECRET_KEY, "response": token, "remoteip": ip}
    ).encode()
    req = urllib.request.Request(TURNSTILE_VERIFY_URL, data=body, method="POST")
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check_captcha(data, action):
    """Mengembalikan response error (tuple/Response) jika verifikasi gagal, atau None jika lolos/nonaktif."""
    if not TURNSTILE_ENABLED:
        return None
    ip = client_ip()
    if attempts_count("captcha", ip, LOGIN_WINDOW) >= CAPTCHA_MAX_PER_IP:
        return too_many(retry_minutes("captcha", ip, LOGIN_WINDOW))

    token = str(data.get("turnstile_token", ""))[:2048]
    if not token:
        attempts_record("captcha", ip)
        return jsonify({"error": "Selesaikan verifikasi keamanan terlebih dahulu", "captcha": True}), 400
    try:
        result = _siteverify(token, ip)
    except Exception:
        # Gagal tutup: jika Cloudflare tidak terjangkau, jangan loloskan permintaan tanpa verifikasi.
        return jsonify({"error": "Layanan verifikasi keamanan sedang tidak tersedia. Coba lagi sebentar.", "captcha": True}), 503

    returned_action = result.get("action")
    if not result.get("success") or (returned_action and returned_action != action):
        attempts_record("captcha", ip)
        return jsonify({"error": "Verifikasi keamanan gagal. Coba lagi.", "captcha": True}), 400
    return None


# ---------- CSRF + header keamanan ----------
def csrf_token():
    if not session.get("csrf"):
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def csrf_protect():
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return None
    origin = request.headers.get("Origin")
    if origin and urlparse(origin).netloc != request.host:
        return jsonify({"error": "Permintaan ditolak (asal tidak cocok)"}), 403
    token = session.get("csrf", "")
    sent = request.headers.get("X-CSRF-Token", "")
    if not token or not hmac.compare_digest(sent, token):
        return jsonify({"error": "Token keamanan tidak valid. Muat ulang halaman lalu coba lagi."}), 403
    return None


@app.after_request
def security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "same-origin"
    resp.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    resp.headers["Content-Security-Policy"] = CSP
    if not request.path.startswith("/static/"):
        resp.headers["Cache-Control"] = "no-store"
    if IS_PROD:
        resp.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return resp


# ---------- Sesi & otorisasi ----------
def load_user():
    """Validasi sesi ke database di SETIAP request: akun dihapus/dinonaktifkan/ganti password langsung berlaku."""
    if hasattr(g, "auth_user"):
        return g.auth_user
    g.auth_user = None
    uid = session.get("user_id")
    if not uid:
        return None
    conn = get_db()
    u = conn.execute(
        "SELECT id, nama, username, role, is_active, must_change_password, session_version FROM users WHERE id = ?",
        (uid,),
    ).fetchone()
    conn.close()
    if not u or not u["is_active"] or u["session_version"] != session.get("sv"):
        session.clear()
        return None
    if u["role"] == "admin":
        t = time.time()
        if t - session.get("last_seen", t) > ADMIN_IDLE_SECONDS or t - session.get("login_at", t) > ADMIN_MAX_SECONDS:
            session.clear()
            return None
        # polling panel admin tidak dihitung sebagai aktivitas
        if not (request.method == "GET" and request.path == "/api/admin/overview"):
            session["last_seen"] = t
    session["user_role"] = u["role"]
    session["user_name"] = u["nama"]
    session["username"] = u["username"]
    g.auth_user = u
    return u


def start_session(user_id, nama, username, role, session_version):
    session.clear()  # mencegah session fixation
    session.permanent = True
    session.update(
        user_id=user_id, user_name=nama, username=username, user_role=role,
        sv=session_version, login_at=time.time(), last_seen=time.time(),
    )
    csrf_token()


PW_CHANGE_ALLOWED = {"/ganti-password", "/api/account/password", "/api/logout"}


def _unauthorized():
    if request.path.startswith("/api/"):
        return jsonify({"error": "Silakan login terlebih dahulu"}), 401
    return redirect(url_for("auth_page"))


def _must_change():
    if request.path.startswith("/api/"):
        return jsonify({"error": "Anda harus mengganti password terlebih dahulu", "must_change_password": True}), 403
    return redirect(url_for("change_password_page"))


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        u = load_user()
        if not u:
            return _unauthorized()
        if u["must_change_password"] and request.path not in PW_CHANGE_ALLOWED:
            return _must_change()
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        u = load_user()
        if not u:
            return _unauthorized()
        if u["role"] != "admin":
            if request.path.startswith("/api/"):
                return jsonify({"error": "Akses ditolak. Khusus admin."}), 403
            return redirect(url_for("index"))
        if u["must_change_password"]:
            return _must_change()
        return f(*args, **kwargs)
    return decorated


def require_admin_password(data):
    """Verifikasi ulang password operator sebelum aksi sensitif. Mengembalikan response error atau None."""
    ident = str(session["user_id"])
    if attempts_count("reauth", ident, LOGIN_WINDOW) >= REAUTH_MAX:
        return too_many(retry_minutes("reauth", ident, LOGIN_WINDOW))
    pw = str(data.get("admin_password", ""))[:128]
    conn = get_db()
    row = conn.execute("SELECT password_hash FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    conn.close()
    if not row or not pw or not check_password_hash(row["password_hash"], pw):
        attempts_record("reauth", ident)
        log_activity(session["user_id"], session.get("username", "admin"), "[Keamanan] Verifikasi password operator gagal")
        return jsonify({"error": "Password operator salah"}), 403
    attempts_clear("reauth", ident)
    return None


# --- Pages ---
@app.route("/")
@login_required
def index():
    u = load_user()
    return render_template("index.html", user_name=u["nama"], is_admin=(u["role"] == "admin"), categories=CATEGORIES)


@app.route("/admin")
@admin_required
def admin_page():
    return render_template("admin.html", user_name=load_user()["nama"])


@app.route("/auth")
def auth_page():
    u = load_user()
    if u:
        return redirect(url_for("change_password_page" if u["must_change_password"] else "index"))
    return render_template("auth.html", turnstile_site_key=TURNSTILE_SITE_KEY if TURNSTILE_ENABLED else "")


@app.route("/ganti-password")
@login_required
def change_password_page():
    u = load_user()
    return render_template("change_password.html", user_name=u["nama"], forced=bool(u["must_change_password"]))


# --- Auth API ---
@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    nama = txt(data.get("nama"), 50)
    username = txt(data.get("username"), 40).lower()
    password = str(data.get("password", ""))
    ip = client_ip()

    if attempts_count("register", ip, 3600) >= REGISTER_MAX_PER_HOUR:
        return too_many(retry_minutes("register", ip, 3600))
    denied = check_captcha(data, "register")
    if denied:
        return denied
    if not nama:
        return jsonify({"error": "Nama panggilan wajib diisi"}), 400
    if not USERNAME_RE.match(username):
        return jsonify({"error": "Username 3-30 karakter: huruf kecil, angka, dan garis bawah (_) saja"}), 400
    pw_error = validate_password(password, username, nama)
    if pw_error:
        return jsonify({"error": pw_error}), 400

    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (nama, username, password_hash, role) VALUES (?, ?, ?, 'user')",
            (nama, username, generate_password_hash(password)),
        )
        user_id = cur.lastrowid
        seed_default_templates(cur, user_id)
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({"error": "Username sudah digunakan, coba yang lain"}), 409
    conn.close()

    attempts_record("register", ip)
    start_session(user_id, nama, username, "user", 0)
    log_activity(user_id, username, "Mendaftar akun baru")
    return jsonify({"message": "Akun berhasil dibuat"}), 201


@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = txt(data.get("username"), 64).lower()
    password = str(data.get("password", ""))[:128]
    ip = client_ip()
    pair = f"{username}|{ip}"

    if attempts_count("login", pair, LOGIN_WINDOW) >= LOGIN_MAX_PER_PAIR:
        return too_many(retry_minutes("login", pair, LOGIN_WINDOW))
    if attempts_count("login_ip", ip, LOGIN_WINDOW) >= LOGIN_MAX_PER_IP:
        return too_many(retry_minutes("login_ip", ip, LOGIN_WINDOW))
    denied = check_captcha(data, "login")  # gagal captcha tidak menghitung percobaan password (tak bisa dipakai mengunci korban)
    if denied:
        return denied

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()

    valid = check_password_hash(user["password_hash"] if user else DUMMY_HASH, password) and user is not None
    if not valid:
        attempts_record("login", pair)
        attempts_record("login_ip", ip)
        if user:
            n = attempts_count("login", pair, LOGIN_WINDOW)
            log_activity(user["id"], user["username"], f"[Keamanan] Login gagal (percobaan ke-{n})")
            if n >= LOGIN_MAX_PER_PAIR:
                log_activity(user["id"], user["username"], "[Keamanan] Login dikunci sementara 15 menit untuk perangkat ini")
        return jsonify({"error": "Username atau password salah"}), 401

    if not user["is_active"]:
        return jsonify({"error": "Akun ini sedang dinonaktifkan oleh admin"}), 403

    attempts_clear("login", pair)
    start_session(user["id"], user["nama"], user["username"], user["role"], user["session_version"])
    log_activity(user["id"], user["username"], "Login ke aplikasi")
    return jsonify({
        "message": "Login berhasil",
        "role": user["role"],
        "must_change_password": bool(user["must_change_password"]),
    })


@app.route("/api/logout", methods=["POST"])
def logout():
    if session.get("user_id"):
        log_activity(session.get("user_id"), session.get("username", "-"), "Keluar dari aplikasi")
    session.clear()
    return jsonify({"message": "Berhasil keluar"})


# --- Account Settings API ---
@app.route("/api/account/profile", methods=["PUT"])
@login_required
def update_profile():
    uid = session["user_id"]
    data = request.get_json(silent=True) or {}
    nama = txt(data.get("nama"), 50)
    if not nama:
        return jsonify({"error": "Nama panggilan tidak boleh kosong"}), 400

    conn = get_db()
    conn.execute("UPDATE users SET nama = ? WHERE id = ?", (nama, uid))
    conn.commit()
    conn.close()

    session["user_name"] = nama
    log_activity(uid, session.get("username", "-"), "Memperbarui nama profil")
    return jsonify({"nama": nama, "message": "Nama profil diperbarui"})


@app.route("/api/account/password", methods=["PUT"])
@login_required
def update_password():
    uid = session["user_id"]
    data = request.get_json(silent=True) or {}
    old_pw = str(data.get("old_password", ""))[:128]
    new_pw = str(data.get("new_password", ""))
    ident = str(uid)

    if attempts_count("pwchange", ident, LOGIN_WINDOW) >= REAUTH_MAX:
        return too_many(retry_minutes("pwchange", ident, LOGIN_WINDOW))

    conn = get_db()
    user = conn.execute(
        "SELECT username, nama, password_hash, session_version FROM users WHERE id = ?", (uid,)
    ).fetchone()
    if not user or not check_password_hash(user["password_hash"], old_pw):
        conn.close()
        attempts_record("pwchange", ident)
        return jsonify({"error": "Password lama tidak sesuai"}), 400

    pw_error = validate_password(new_pw, user["username"], user["nama"])
    if pw_error:
        conn.close()
        return jsonify({"error": pw_error}), 400
    if new_pw == old_pw:
        conn.close()
        return jsonify({"error": "Password baru harus berbeda dari password lama"}), 400

    new_sv = user["session_version"] + 1  # mengeluarkan sesi di perangkat lain
    conn.execute(
        "UPDATE users SET password_hash = ?, must_change_password = 0, session_version = ? WHERE id = ?",
        (generate_password_hash(new_pw), new_sv, uid),
    )
    conn.commit()
    conn.close()

    attempts_clear("pwchange", ident)
    session["sv"] = new_sv
    log_activity(uid, user["username"], "[Keamanan] Password akun diganti (sesi lain dikeluarkan)")
    return jsonify({"message": "Password berhasil diubah"})


# --- User Data API ---
@app.route("/api/data", methods=["GET"])
@login_required
def get_all_data():
    uid = session["user_id"]
    conn = get_db()
    user = conn.execute(
        "SELECT nama, username, daily_limit, is_active FROM users WHERE id = ?", (uid,)
    ).fetchone()
    if not user or not user["is_active"]:
        conn.close()
        session.clear()
        return jsonify({"error": "Sesi tidak valid"}), 401

    transactions = [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM transactions WHERE user_id = ? ORDER BY tanggal DESC, id DESC",
            (uid,),
        ).fetchall()
    ]
    goals = [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM savings_goals WHERE user_id = ? ORDER BY id DESC",
            (uid,),
        ).fetchall()
    ]
    debts = [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM debts WHERE user_id = ? ORDER BY CASE WHEN status = 'belum' THEN 0 ELSE 1 END, id DESC",
            (uid,),
        ).fetchall()
    ]
    quick_templates = [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM quick_templates WHERE user_id = ? ORDER BY id ASC",
            (uid,),
        ).fetchall()
    ]
    ann_row = conn.execute(
        "SELECT value FROM app_settings WHERE key = 'announcement'"
    ).fetchone()
    announcement = ann_row["value"] if ann_row else ""
    conn.close()

    return jsonify({
        "user_name": user["nama"],
        "username": user["username"],
        "transactions": transactions,
        "goals": goals,
        "debts": debts,
        "quick_templates": quick_templates,
        "daily_limit": user["daily_limit"],
        "announcement": announcement,
    })


@app.route("/api/transactions", methods=["POST"])
@login_required
def add_transaction():
    uid = session["user_id"]
    data = request.get_json(silent=True) or {}
    tipe = data.get("tipe")
    nominal = to_int(data.get("nominal"))
    kategori = txt(data.get("kategori"), 60)
    tanggal = safe_date(data.get("tanggal")) or date.today().isoformat()
    catatan = txt(data.get("catatan"), 200)

    if tipe not in ("masuk", "keluar") or nominal <= 0 or not kategori:
        return jsonify({"error": "Data transaksi tidak valid"}), 400
    if not category_ok(tipe, kategori):
        return jsonify({"error": "Kategori tidak sesuai dengan jenis transaksi"}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO transactions (user_id, tipe, nominal, kategori, tanggal, catatan) VALUES (?, ?, ?, ?, ?, ?)",
        (uid, tipe, nominal, kategori, tanggal, catatan),
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    log_activity(uid, session.get("username", "-"), f"Menambah transaksi ({tipe})")
    return jsonify({"id": new_id, "message": "Transaksi berhasil disimpan"}), 201


@app.route("/api/transactions/<int:tx_id>", methods=["PUT"])
@login_required
def edit_transaction(tx_id):
    uid = session["user_id"]
    data = request.get_json(silent=True) or {}
    tipe = data.get("tipe")
    nominal = to_int(data.get("nominal"))
    kategori = txt(data.get("kategori"), 60)
    tanggal = safe_date(data.get("tanggal")) or ""
    catatan = txt(data.get("catatan"), 200)

    if tipe not in ("masuk", "keluar") or nominal <= 0 or not kategori or not tanggal:
        return jsonify({"error": "Data transaksi tidak valid"}), 400

    conn = get_db()
    existing = conn.execute(
        "SELECT tipe, kategori FROM transactions WHERE id = ? AND user_id = ?", (tx_id, uid)
    ).fetchone()
    conn.close()
    if not existing:
        return jsonify({"error": "Transaksi tidak ditemukan"}), 404
    unchanged_legacy = existing["tipe"] == tipe and existing["kategori"] == kategori
    if not category_ok(tipe, kategori) and not unchanged_legacy:
        return jsonify({"error": "Kategori tidak sesuai dengan jenis transaksi"}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE transactions
        SET tipe = ?, nominal = ?, kategori = ?, tanggal = ?, catatan = ?
        WHERE id = ? AND user_id = ?
        """,
        (tipe, nominal, kategori, tanggal, catatan, tx_id, uid),
    )
    updated = cur.rowcount
    conn.commit()
    conn.close()

    if updated == 0:
        return jsonify({"error": "Transaksi tidak ditemukan"}), 404

    log_activity(uid, session.get("username", "-"), f"Mengedit transaksi ({tipe})")
    return jsonify({"message": "Transaksi berhasil diperbarui"})


@app.route("/api/transactions/<int:tx_id>", methods=["DELETE"])
@login_required
def delete_transaction(tx_id):
    uid = session["user_id"]
    conn = get_db()
    conn.execute("DELETE FROM transactions WHERE id = ? AND user_id = ?", (tx_id, uid))
    conn.commit()
    conn.close()
    log_activity(uid, session.get("username", "-"), "Menghapus transaksi")
    return jsonify({"message": "Transaksi dihapus"})


@app.route("/api/transactions/export", methods=["GET"])
@login_required
def export_transactions_csv():
    uid = session["user_id"]
    conn = get_db()
    rows = conn.execute(
        "SELECT tanggal, tipe, kategori, nominal, catatan FROM transactions WHERE user_id = ? ORDER BY tanggal DESC, id DESC",
        (uid,),
    ).fetchall()
    conn.close()

    output = io.StringIO()
    output.write("﻿")
    writer = csv.writer(output)
    writer.writerow(["Tanggal", "Tipe", "Kategori", "Nominal (Rp)", "Catatan"])
    for r in rows:
        tipe_label = "Pemasukan" if r["tipe"] == "masuk" else "Pengeluaran"
        writer.writerow([r["tanggal"], tipe_label, csv_safe(r["kategori"]), r["nominal"], csv_safe(r["catatan"])])

    log_activity(uid, session.get("username", "-"), "Mengunduh laporan transaksi (CSV)")
    safe_user = re.sub(r"[^a-z0-9_-]", "", str(session.get("username", "user")).lower()) or "user"
    filename = f"sakuku-laporan-{safe_user}-{date.today().isoformat()}.csv"
    return Response(
        output.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# --- Quick Templates API ---
@app.route("/api/templates", methods=["POST"])
@login_required
def add_template():
    uid = session["user_id"]
    data = request.get_json(silent=True) or {}
    nama = txt(data.get("nama"), 60)
    tipe = data.get("tipe", "keluar")
    nominal = to_int(data.get("nominal"))
    kategori = txt(data.get("kategori"), 60)

    if not nama or tipe not in ("masuk", "keluar") or nominal <= 0 or not kategori:
        return jsonify({"error": "Data template tidak valid"}), 400
    if not category_ok(tipe, kategori):
        return jsonify({"error": "Kategori tidak sesuai dengan jenis transaksi"}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO quick_templates (user_id, nama, tipe, nominal, kategori) VALUES (?, ?, ?, ?, ?)",
        (uid, nama, tipe, nominal, kategori),
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    log_activity(uid, session.get("username", "-"), "Menambah template catat cepat")
    return jsonify({"id": new_id, "message": "Template ditambahkan"}), 201


@app.route("/api/templates/<int:tpl_id>", methods=["DELETE"])
@login_required
def delete_template(tpl_id):
    uid = session["user_id"]
    conn = get_db()
    conn.execute("DELETE FROM quick_templates WHERE id = ? AND user_id = ?", (tpl_id, uid))
    conn.commit()
    conn.close()
    return jsonify({"message": "Template dihapus"})


# --- Debts (Hutang / Piutang) API ---
@app.route("/api/debts", methods=["POST"])
@login_required
def add_debt():
    uid = session["user_id"]
    data = request.get_json(silent=True) or {}
    tipe = data.get("tipe")
    nama_orang = txt(data.get("nama_orang"), 60)
    nominal = to_int(data.get("nominal"))
    catatan = txt(data.get("catatan"), 200)

    if tipe not in ("hutang", "piutang") or not nama_orang or nominal <= 0:
        return jsonify({"error": "Data hutang/piutang tidak valid"}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO debts (user_id, tipe, nama_orang, nominal, catatan, status) VALUES (?, ?, ?, ?, ?, 'belum')",
        (uid, tipe, nama_orang, nominal, catatan),
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    log_activity(uid, session.get("username", "-"), f"Mencatat {tipe} baru")
    return jsonify({"id": new_id, "message": "Catatan berhasil disimpan"}), 201


@app.route("/api/debts/<int:debt_id>/settle", methods=["PATCH"])
@login_required
def settle_debt(debt_id):
    uid = session["user_id"]
    data = request.get_json(silent=True) or {}
    catat_transaksi = bool(data.get("catat_transaksi", False))
    tanggal = safe_date(data.get("tanggal")) or date.today().isoformat()

    conn = get_db()
    debt = conn.execute(
        "SELECT * FROM debts WHERE id = ? AND user_id = ?", (debt_id, uid)
    ).fetchone()
    if not debt:
        conn.close()
        return jsonify({"error": "Data tidak ditemukan"}), 404
    if debt["status"] == "lunas":
        conn.close()
        return jsonify({"message": "Sudah lunas"})

    conn.execute("UPDATE debts SET status = 'lunas' WHERE id = ? AND user_id = ?", (debt_id, uid))

    if catat_transaksi:
        tx_tipe = "keluar" if debt["tipe"] == "hutang" else "masuk"
        tx_catatan = (
            f"Bayar hutang ke {debt['nama_orang']}"
            if debt["tipe"] == "hutang"
            else f"Pelunasan piutang dari {debt['nama_orang']}"
        )
        conn.execute(
            "INSERT INTO transactions (user_id, tipe, nominal, kategori, tanggal, catatan) VALUES (?, ?, ?, 'Lainnya', ?, ?)",
            (uid, tx_tipe, debt["nominal"], tanggal, tx_catatan),
        )

    conn.commit()
    conn.close()
    log_activity(uid, session.get("username", "-"), f"Melunasi {debt['tipe']}")
    return jsonify({"message": "Ditandai lunas"})


@app.route("/api/debts/<int:debt_id>", methods=["DELETE"])
@login_required
def delete_debt(debt_id):
    uid = session["user_id"]
    conn = get_db()
    conn.execute("DELETE FROM debts WHERE id = ? AND user_id = ?", (debt_id, uid))
    conn.commit()
    conn.close()
    log_activity(uid, session.get("username", "-"), "Menghapus catatan hutang/piutang")
    return jsonify({"message": "Catatan dihapus"})


# --- Goals API ---
@app.route("/api/goals", methods=["POST"])
@login_required
def add_goal():
    uid = session["user_id"]
    data = request.get_json(silent=True) or {}
    nama = txt(data.get("nama"), 60)
    target = to_int(data.get("target"))

    if not nama or target <= 0:
        return jsonify({"error": "Data target tidak valid"}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO savings_goals (user_id, nama, target, terkumpul) VALUES (?, ?, ?, 0)",
        (uid, nama, target),
    )
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    log_activity(uid, session.get("username", "-"), "Membuat target tabungan baru")
    return jsonify({"id": new_id, "message": "Target tabungan ditambahkan"}), 201


@app.route("/api/goals/<int:goal_id>/add", methods=["PATCH"])
@login_required
def add_savings(goal_id):
    uid = session["user_id"]
    data = request.get_json(silent=True) or {}
    jumlah = to_int(data.get("jumlah"))
    potong_saldo = bool(data.get("potong_saldo", False))
    tanggal = safe_date(data.get("tanggal")) or date.today().isoformat()

    if jumlah <= 0:
        return jsonify({"error": "Nominal harus lebih dari 0"}), 400

    conn = get_db()
    goal = conn.execute(
        "SELECT id, nama FROM savings_goals WHERE id = ? AND user_id = ?",
        (goal_id, uid),
    ).fetchone()
    if not goal:
        conn.close()
        return jsonify({"error": "Target tabungan tidak ditemukan"}), 404

    conn.execute(
        "UPDATE savings_goals SET terkumpul = terkumpul + ? WHERE id = ? AND user_id = ?",
        (jumlah, goal_id, uid),
    )

    if potong_saldo:
        conn.execute(
            "INSERT INTO transactions (user_id, tipe, nominal, kategori, tanggal, catatan) VALUES (?, 'keluar', ?, 'Tabungan', ?, ?)",
            (uid, jumlah, tanggal, f"Setoran target: {goal['nama']}"),
        )

    conn.commit()
    conn.close()
    aksi_note = "Menambah setoran tabungan (potong saldo)" if potong_saldo else "Menambah setoran target tabungan"
    log_activity(uid, session.get("username", "-"), aksi_note)
    return jsonify({"message": "Tabungan berhasil ditambahkan"})


@app.route("/api/goals/<int:goal_id>", methods=["DELETE"])
@login_required
def delete_goal(goal_id):
    uid = session["user_id"]
    conn = get_db()
    conn.execute("DELETE FROM savings_goals WHERE id = ? AND user_id = ?", (goal_id, uid))
    conn.commit()
    conn.close()
    log_activity(uid, session.get("username", "-"), "Menghapus target tabungan")
    return jsonify({"message": "Target dihapus"})


@app.route("/api/settings/daily-limit", methods=["PUT"])
@login_required
def update_daily_limit():
    uid = session["user_id"]
    data = request.get_json(silent=True) or {}
    limit_val = to_int(data.get("daily_limit"))
    if limit_val <= 0:
        return jsonify({"error": "Batas harian harus lebih dari 0"}), 400

    conn = get_db()
    conn.execute("UPDATE users SET daily_limit = ? WHERE id = ?", (limit_val, uid))
    conn.commit()
    conn.close()
    log_activity(uid, session.get("username", "-"), "Mengubah batas pengeluaran harian")
    return jsonify({"daily_limit": limit_val, "message": "Batas harian diperbarui"})


# --- Admin / Operator API ---
@app.route("/api/admin/overview", methods=["GET"])
@admin_required
def admin_overview():
    conn = get_db()
    total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    active_users = conn.execute("SELECT COUNT(*) FROM users WHERE is_active = 1").fetchone()[0]
    total_tx = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    total_goals = conn.execute("SELECT COUNT(*) FROM savings_goals").fetchone()[0]

    since = time.time()
    failed_24h = conn.execute(
        "SELECT COUNT(*) FROM auth_attempts WHERE scope = 'login' AND ts > ?", (since - 86400,)
    ).fetchone()[0]
    locked_now = conn.execute(
        "SELECT COUNT(*) FROM (SELECT ident FROM auth_attempts WHERE scope = 'login' AND ts > ? "
        "GROUP BY ident HAVING COUNT(*) >= ?)",
        (since - LOGIN_WINDOW, LOGIN_MAX_PER_PAIR),
    ).fetchone()[0]
    pending_pw = conn.execute("SELECT COUNT(*) FROM users WHERE must_change_password = 1").fetchone()[0]

    users = [
        dict(row)
        for row in conn.execute(
            """
            SELECT u.id, u.nama, u.username, u.role, u.is_active, u.created_at, u.must_change_password,
                   (SELECT COUNT(*) FROM transactions t WHERE t.user_id = u.id) AS tx_count
            FROM users u
            ORDER BY u.id ASC
            """
        ).fetchall()
    ]

    logs = [
        dict(row)
        for row in conn.execute(
            "SELECT id, username, aksi, created_at FROM activity_logs ORDER BY id DESC LIMIT 50"
        ).fetchall()
    ]

    ann_row = conn.execute("SELECT value FROM app_settings WHERE key = 'announcement'").fetchone()
    announcement = ann_row["value"] if ann_row else ""
    conn.close()

    return jsonify({
        "stats": {
            "total_users": total_users,
            "active_users": active_users,
            "total_transactions": total_tx,
            "total_goals": total_goals,
            "failed_logins_24h": failed_24h,
            "locked_now": locked_now,
            "pending_pw_change": pending_pw,
        },
        "users": users,
        "logs": logs,
        "announcement": announcement,
        "current_admin_id": session["user_id"],
    })


def _admin_target(target_id):
    """Ambil akun target. Operator tidak boleh mengelola operator lain maupun dirinya lewat panel ini."""
    conn = get_db()
    user = conn.execute(
        "SELECT id, username, role, is_active, session_version FROM users WHERE id = ?", (target_id,)
    ).fetchone()
    conn.close()
    if not user:
        return None, (jsonify({"error": "Pengguna tidak ditemukan"}), 404)
    if user["role"] == "admin":
        return None, (jsonify({"error": "Akun operator tidak dapat dikelola lewat panel ini"}), 403)
    return user, None


@app.route("/api/admin/users/<int:target_id>/toggle-status", methods=["PATCH"])
@admin_required
def admin_toggle_user(target_id):
    if target_id == session["user_id"]:
        return jsonify({"error": "Tidak bisa menonaktifkan akun sendiri"}), 400
    data = request.get_json(silent=True) or {}
    user, err = _admin_target(target_id)
    if err:
        return err
    if user["is_active"]:  # menonaktifkan = aksi sensitif
        denied = require_admin_password(data)
        if denied:
            return denied

    new_status = 0 if user["is_active"] else 1
    conn = get_db()
    conn.execute(
        "UPDATE users SET is_active = ?, session_version = session_version + 1 WHERE id = ?",
        (new_status, target_id),
    )
    conn.commit()
    conn.close()
    status_label = "Mengaktifkan" if new_status else "Menonaktifkan"
    log_activity(session["user_id"], session.get("username", "admin"), f"{status_label} akun @{user['username']}")
    return jsonify({"is_active": new_status, "message": "Status akun diperbarui"})


@app.route("/api/admin/users/<int:target_id>/reset-password", methods=["PATCH"])
@admin_required
def admin_reset_password(target_id):
    if target_id == session["user_id"]:
        return jsonify({"error": "Ubah password sendiri lewat Pengaturan Akun"}), 400
    data = request.get_json(silent=True) or {}
    user, err = _admin_target(target_id)
    if err:
        return err
    denied = require_admin_password(data)
    if denied:
        return denied

    temp_pw = random_password(12)  # dibuat sistem, operator tidak memilih password pengguna
    conn = get_db()
    conn.execute(
        "UPDATE users SET password_hash = ?, must_change_password = 1, session_version = session_version + 1 "
        "WHERE id = ?",
        (generate_password_hash(temp_pw), target_id),
    )
    conn.execute(
        "DELETE FROM auth_attempts WHERE scope = 'login' AND substr(ident, 1, length(?)) = ?",
        (user["username"] + "|", user["username"] + "|"),
    )
    conn.commit()
    conn.close()
    log_activity(session["user_id"], session.get("username", "admin"), f"[Keamanan] Mereset password @{user['username']}")
    return jsonify({"temp_password": temp_pw, "message": "Password sementara dibuat"})


@app.route("/api/admin/users/<int:target_id>", methods=["DELETE"])
@admin_required
def admin_delete_user(target_id):
    if target_id == session["user_id"]:
        return jsonify({"error": "Tidak bisa menghapus akun sendiri"}), 400
    data = request.get_json(silent=True) or {}
    user, err = _admin_target(target_id)
    if err:
        return err
    denied = require_admin_password(data)
    if denied:
        return denied

    conn = get_db()
    conn.execute("DELETE FROM users WHERE id = ?", (target_id,))
    conn.commit()
    conn.close()
    log_activity(session["user_id"], session.get("username", "admin"), f"[Keamanan] Menghapus akun @{user['username']}")
    return jsonify({"message": "Akun pengguna dihapus"})


@app.route("/api/admin/announcement", methods=["PUT"])
@admin_required
def admin_update_announcement():
    data = request.get_json(silent=True) or {}
    text = txt(data.get("announcement"), 300)

    conn = get_db()
    conn.execute(
        "INSERT INTO app_settings (key, value) VALUES ('announcement', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (text,),
    )
    conn.commit()
    conn.close()
    log_activity(session["user_id"], session.get("username", "admin"), "Memperbarui pengumuman global")
    return jsonify({"announcement": text, "message": "Pengumuman diperbarui"})


if bool(TURNSTILE_SITE_KEY) != bool(TURNSTILE_SECRET_KEY):
    print("[PERINGATAN] Hanya satu dari TURNSTILE_SITE_KEY / TURNSTILE_SECRET_KEY yang diisi. Anti-robot TIDAK aktif.")
elif not TURNSTILE_ENABLED and IS_PROD:
    print("[PERINGATAN] Mode production tanpa anti-robot. Isi TURNSTILE_SITE_KEY dan TURNSTILE_SECRET_KEY.")

init_db()

if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG") == "1"  # debugger Werkzeug = eksekusi kode jarak jauh; jangan dinyalakan di server publik
    if debug:
        print("[PERINGATAN] Mode debug aktif. Jangan dipakai di server yang bisa diakses orang lain.")
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
        debug=debug,
    )
