# SakuKu v4 — Full Stack Real-Time + Panel Operator (Flask + SQLite)

Versi v4 menambahkan **Catatan Hutang/Piutang (Kasbon)**, **Filter per Bulan**, dan **Catat Cepat 1-Klik (Quick Add)** melengkapi seluruh fitur v3.

## Akun Operator (PENTING)
Tidak ada lagi password bawaan. Saat **pertama kali** dijalankan, aplikasi membuat akun `admin` dengan
**password acak** yang dicetak **satu kali** di terminal. Salin, lalu login — kamu akan diminta menggantinya.

- Mau menentukan sendiri? Jalankan dengan `ADMIN_PASSWORD="PasswordKuat123"` (harus lolos aturan password).
- Punya database lama yang masih `admin` / `admin123`? Akun itu otomatis **dipaksa ganti password** saat login.
- Lupa password operator? Hapus akun admin dari `sakuku.db` lalu jalankan ulang; akun baru dibuat dengan password acak.

## Fitur Baru di v4
- **Hutang & Piutang (Kasbon Teman)**: Catat siapa yang pinjam uang atau kamu pinjam ke siapa, lengkap dengan tombol **Lunas** (bisa otomatis menambah/memotong saldo).
- **Filter per Bulan**: Pilih bulan tertentu di Dashboard untuk melihat saldo, pengeluaran per kategori, dan transaksi khusus bulan tersebut.
- **Catat Cepat (1-Klik / Quick Add)**: Pintasan pengeluaran/pemasukan rutin (bawaan: *Parkir*, *Jajan Kantin*, *Uang Kas*, dan bisa tambah/hapus template sendiri).

## Cara Menjalankan
1. Pasang dependensi: `pip install -r requirements.txt`. Ekstrak folder `sakuku-v4` (jika sudah punya data di v3, cukup salin file `sakuku.db` lama ke folder `sakuku-v4`—tabel baru akan dibuat otomatis).
2. Jalankan `python app.py` di terminal / VS Code.
3. Buka `http://127.0.0.1:5000` di browser.

## Desain (v4.1)
- Palet "kertas buku kas": krem hangat, hijau pine (merek), terracotta (pengeluaran), ochre (peringatan). Semua warna didefinisikan **sekali** di `static/js/tailwind-config.js`.
- Font: Bricolage Grotesque (judul & angka) + Instrument Sans (isi).
- Dark mode memakai netral hangat, bukan abu-biru. Tombol utama dibuat lebih terang agar tetap terbaca.
- Ingin ganti warna merek? Ubah skala `brand` di `tailwind-config.js` — seluruh halaman ikut berubah.

## Keamanan (v4.2)
**Untuk pengguna**
- Password minimal 8 karakter, wajib huruf + angka, menolak kata umum dan yang memuat username.
- Username dibatasi huruf kecil, angka, `_` (menutup celah penyisipan script ke panel operator).
- Login dibatasi: 5 salah dari satu perangkat = dikunci 15 menit (pemilik asli dari perangkat lain tidak ikut terkunci). Pendaftaran massal juga dibatasi.
- Ganti password otomatis mengeluarkan sesi di perangkat lain. Akun yang dinonaktifkan/dihapus langsung terpental.
- Perlindungan CSRF di semua aksi, cookie sesi `HttpOnly` + `SameSite=Lax`, unduhan CSV aman dari formula injection.

**Untuk operator**
- Aksi sensitif (reset password, nonaktifkan, hapus akun) meminta **password operator lagi**; salah berulang = dikunci.
- Reset password menghasilkan **password sementara acak** (tampil sekali); pengguna wajib menggantinya.
- Operator tidak bisa mengelola operator lain; sesi operator habis setelah 20 menit diam / 8 jam.
- Panel menampilkan login gagal 24 jam, akun yang sedang terkunci, dan peristiwa `[Keamanan]` di log.

**Saat dipasang di server publik**
- Wajib HTTPS, lalu jalankan dengan `SAKUKU_ENV=production` (mengaktifkan cookie `Secure` dan HSTS).
- Di balik Nginx/Cloudflare tambahkan `TRUST_PROXY=1` agar IP asli terbaca (kalau tidak, pembatas login memakai IP proxy).
- Gunakan server produksi (mis. `gunicorn app:app`), bukan `python app.py`. Mode debug hanya menyala bila `FLASK_DEBUG=1`.
- Simpan cadangan `sakuku.db`; file `.secret_key` jangan dibagikan (sudah masuk `.gitignore`).

## Anti-robot: Cloudflare Turnstile (v4.4)
Dipasang di **Masuk** (termasuk login operator) dan **Daftar Akun**. Verifikasi dilakukan di server, bukan hanya di browser.
Fitur ini **mati otomatis** bila kunci tidak diisi, jadi pengembangan lokal tidak terganggu.

**Cara mengaktifkan**
1. Masuk ke dashboard Cloudflare (akun gratis) → **Turnstile** → **Add widget**.
2. Isi nama dan **domain situsmu** (mis. `sakuku.example.com`), mode **Managed**.
3. Salin *Site Key* dan *Secret Key*, lalu jalankan aplikasi dengan:
```
TURNSTILE_SITE_KEY="0x4AAAA...."
TURNSTILE_SECRET_KEY="0x4AAAA...."
```
Keduanya harus diisi. Jangan pernah menaruh Secret Key di kode atau repositori.

**Mencoba di lokal:** Cloudflare menyediakan *dummy key* untuk pengujian (selalu lolos / selalu diblokir). Lihat dokumentasi Turnstile bagian "Testing".

**Perilaku keamanan**
- Token dipakai sekali dan terikat pada aksi (token Masuk tidak bisa dipakai untuk Daftar).
- Jika Cloudflare tidak terjangkau, permintaan **ditolak** (gagal tutup), bukan diloloskan.
- Gagal verifikasi robot **tidak** menambah hitungan kunci password, sehingga robot tidak bisa mengunci akun korban.
- Percobaan verifikasi gagal dibatasi 20 kali per IP per 15 menit.
- CSP otomatis mengizinkan `challenges.cloudflare.com` hanya ketika Turnstile aktif.
