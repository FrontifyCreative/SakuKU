let state = {
  userName: "",
  transactions: [],
  goals: [],
  debts: [],
  quickTemplates: [],
  dailyLimit: 30000,
  selectedMonth: "all",
};

let expenseChart = null;
let lastDataHash = "";

// --- Helpers ---
const formatRupiah = (angka) =>
  new Intl.NumberFormat("id-ID", {
    style: "currency",
    currency: "IDR",
    maximumFractionDigits: 0,
  }).format(angka);

const getTodayDate = () => {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
};

const formatMonthLabel = (ym) => {
  const [y, m] = ym.split("-");
  const bulan = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"];
  return `${bulan[Number(m) - 1] || m} ${y}`;
};

const escapeHtml = (text) =>
  String(text ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const showToast = (message, type = "success") => {
  const container = document.getElementById("toast-container");
  const toast = document.createElement("div");
  const bg = type === "error" ? "bg-rose-600" : "bg-slate-900 dark:bg-brand-500";
  toast.className = `toast-enter ${bg} text-white px-4 py-2.5 rounded-xl text-xs font-semibold shadow-lg`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), 2800);
};

// --- Modal Controls ---
window.openModal = (id) => {
  const el = document.getElementById(id);
  if (id === "modal-limit") {
    document.getElementById("input-daily-limit").value = state.dailyLimit;
  }
  el.classList.remove("hidden");
  el.classList.add("flex");
};

// Kategori mengikuti tipe: Pemasukan hanya menampilkan kategori pemasukan, Pengeluaran hanya kategori pengeluaran.
// Daftarnya berasal dari server (window.CATEGORIES) sehingga selalu sama dengan aturan validasi.
const fillCategories = (select, tipe, selected) => {
  const list = [...(window.CATEGORIES?.[tipe] || [])];
  if (selected && !list.includes(selected)) list.push(selected); // data lama tetap terbaca saat diedit
  select.innerHTML = list.map((c) => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join("");
  select.value = selected && list.includes(selected) ? selected : list[0];
};
const syncTxCategories = (selected) =>
  fillCategories(document.getElementById("kategori"), document.getElementById("tipe").value, selected);
const syncTplCategories = (selected) =>
  fillCategories(document.getElementById("tpl-kategori"), document.getElementById("tpl-tipe").value, selected);

window.closeModal = (id) => {
  const el = document.getElementById(id);
  el.classList.add("hidden");
  el.classList.remove("flex");
};

window.openNewTransactionModal = (defaultType = "") => {
  document.getElementById("edit-tx-id").value = "";
  document.getElementById("form-transaksi").reset();
  document.getElementById("tanggal").value = getTodayDate();
  if (defaultType === "masuk") {
    document.getElementById("tipe").value = "masuk";
    document.getElementById("modal-tx-title").textContent = "Tambah Pemasukan";
    document.getElementById("btn-submit-tx").textContent = "Simpan Pemasukan";
  } else if (defaultType === "keluar") {
    document.getElementById("tipe").value = "keluar";
    document.getElementById("modal-tx-title").textContent = "Catat Pengeluaran";
    document.getElementById("btn-submit-tx").textContent = "Simpan Pengeluaran";
  } else {
    document.getElementById("modal-tx-title").textContent = "Catat Transaksi Baru";
    document.getElementById("btn-submit-tx").textContent = "Simpan Transaksi";
  }
  syncTxCategories();
  openModal("modal-transaksi");
};

window.openEditTransactionModal = (id) => {
  const tx = state.transactions.find((t) => t.id === id);
  if (!tx) return;

  document.getElementById("edit-tx-id").value = tx.id;
  document.getElementById("modal-tx-title").textContent = "Edit Transaksi";
  document.getElementById("btn-submit-tx").textContent = "Simpan Perubahan";
  document.getElementById("tipe").value = tx.tipe;
  document.getElementById("nominal").value = tx.nominal;
  syncTxCategories(tx.kategori);
  document.getElementById("tanggal").value = tx.tanggal;
  document.getElementById("catatan").value = tx.catatan || "";
  openModal("modal-transaksi");
};

window.openSetorModal = (goalId) => {
  const goal = state.goals.find((g) => g.id === goalId);
  if (!goal) return;

  document.getElementById("setor-goal-id").value = goal.id;
  document.getElementById("setor-goal-name").textContent = `Target: ${goal.nama}`;
  document.getElementById("setor-nominal").value = "";
  document.getElementById("setor-potong-saldo").checked = true;
  openModal("modal-setor");
};

window.openAccountModal = () => {
  document.getElementById("input-profile-nama").value = state.userName || document.getElementById("user-greeting").textContent;
  document.getElementById("form-password").reset();
  openModal("modal-akun");
};

// --- Theme Toggle ---
const initTheme = () => {
  const saved = localStorage.getItem("sakuku_theme");
  if (saved === "dark") document.documentElement.classList.add("dark");
};

const toggleTheme = () => {
  const isDark = document.documentElement.classList.toggle("dark");
  localStorage.setItem("sakuku_theme", isDark ? "dark" : "light");
  renderChart();
};

document.getElementById("btn-theme-desktop")?.addEventListener("click", toggleTheme);
document.getElementById("btn-theme-mobile")?.addEventListener("click", toggleTheme);

// --- View Navigation ---
window.switchView = (viewName) => {
  document.querySelectorAll(".view-section").forEach((s) => s.classList.add("hidden"));
  document.getElementById(`view-${viewName}`).classList.remove("hidden");

  document.querySelectorAll(".nav-btn").forEach((btn) => {
    const active = btn.dataset.view === viewName;
    btn.className = active
      ? "nav-btn active w-full flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-sm font-semibold transition-all bg-brand-50 text-brand-600 dark:bg-brand-400/15 dark:text-brand-300"
      : "nav-btn w-full flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-sm font-medium text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition-all";
  });

  document.querySelectorAll(".mobile-nav-btn").forEach((btn) => {
    const active = btn.dataset.view === viewName;
    btn.className = active
      ? "mobile-nav-btn relative after:absolute after:-top-2.5 after:left-1/2 after:-translate-x-1/2 after:h-[3px] after:w-8 after:rounded-full after:bg-brand-600 dark:after:bg-brand-300 flex flex-col items-center gap-1 text-xs font-semibold text-brand-600 dark:text-brand-300"
      : "mobile-nav-btn flex flex-col items-center gap-1 text-xs font-medium text-slate-500 dark:text-slate-400";
  });
};

document.querySelectorAll(".nav-btn, .mobile-nav-btn").forEach((btn) => {
  btn.addEventListener("click", () => switchView(btn.dataset.view));
});

// --- Month Filter Helper ---
const getFilteredTransactionsByMonth = () => {
  if (state.selectedMonth === "all") return state.transactions;
  return state.transactions.filter((t) => t.tanggal && t.tanggal.startsWith(state.selectedMonth));
};

const renderMonthFilterOptions = () => {
  const select = document.getElementById("month-filter");
  const monthsSet = new Set([getTodayDate().slice(0, 7)]);
  state.transactions.forEach((t) => {
    if (t.tanggal && t.tanggal.length >= 7) monthsSet.add(t.tanggal.slice(0, 7));
  });
  const months = Array.from(monthsSet).sort().reverse();

  const currentVal = state.selectedMonth;
  select.innerHTML =
    `<option value="all">Semua Waktu</option>` +
    months.map((m) => `<option value="${m}">${formatMonthLabel(m)}</option>`).join("");
  select.value = months.includes(currentVal) || currentVal === "all" ? currentVal : "all";
};

// --- Fetch Data from Flask Backend (Real-Time Smart Polling) ---
const fetchData = async (force = false) => {
  try {
    const res = await fetch("/api/data");
    if (res.status === 401) { window.location.href = "/auth"; return; }
    const data = await res.json();

    const currentHash = JSON.stringify(data);
    if (!force && currentHash === lastDataHash) return;
    lastDataHash = currentHash;

    state.userName = data.user_name || "Pengguna";
    state.transactions = data.transactions || [];
    state.goals = data.goals || [];
    state.debts = data.debts || [];
    state.quickTemplates = data.quick_templates || [];
    state.dailyLimit = data.daily_limit || 30000;

    document.getElementById("user-greeting").textContent = state.userName;

    const banner = document.getElementById("announcement-banner");
    const bannerText = document.getElementById("announcement-text");
    if (data.announcement && data.announcement.trim()) {
      bannerText.textContent = data.announcement;
      banner.classList.remove("hidden");
    } else {
      banner.classList.add("hidden");
    }

    renderMonthFilterOptions();
    renderAll();
  } catch (err) {
    if (force) showToast("Gagal memuat data dari server", "error");
  }
};

// --- Render Summary & Chart ---
const renderSummary = () => {
  const scopedTx = getFilteredTransactionsByMonth();
  let totalMasuk = 0;
  let totalKeluar = 0;
  let keluarHariIni = 0;
  const today = getTodayDate();

  scopedTx.forEach((t) => {
    if (t.tipe === "masuk") totalMasuk += t.nominal;
    else totalKeluar += t.nominal;
  });

  state.transactions.forEach((t) => {
    if (t.tipe === "keluar" && t.tanggal === today) keluarHariIni += t.nominal;
  });

  const saldo = totalMasuk - totalKeluar;
  document.getElementById("total-saldo").textContent = formatRupiah(saldo);
  const emptyBanner = document.getElementById("empty-saldo-banner");
  if (emptyBanner) {
    emptyBanner.classList.toggle("hidden", state.transactions.length > 0);
  }
  document.getElementById("total-masuk").textContent = formatRupiah(totalMasuk);
  document.getElementById("total-keluar").textContent = formatRupiah(totalKeluar);

  const persen = state.dailyLimit > 0 ? Math.min((keluarHariIni / state.dailyLimit) * 100, 100) : 100;
  const bar = document.getElementById("daily-progress-bar");
  const badge = document.getElementById("daily-status-badge");

  document.getElementById("daily-spent-text").textContent =
    `${formatRupiah(keluarHariIni)} / ${formatRupiah(state.dailyLimit)}`;
  bar.style.width = `${persen}%`;

  if (keluarHariIni > state.dailyLimit) {
    bar.className = "h-full bg-rose-500 rounded-full transition-all duration-300";
    badge.className = "px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-100 text-rose-700 dark:bg-rose-500/20 dark:text-rose-300";
    badge.textContent = "Melebihi Batas";
  } else if (persen >= 75) {
    bar.className = "h-full bg-amber-500 rounded-full transition-all duration-300";
    badge.className = "px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-300";
    badge.textContent = "Hampir Batas";
  } else {
    bar.className = "h-full bg-emerald-500 rounded-full transition-all duration-300";
    badge.className = "px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300";
    badge.textContent = "Aman";
  }
};

const renderChart = () => {
  const ctx = document.getElementById("expenseChart");
  const emptyText = document.getElementById("chart-empty");

  const totalsByCategory = {};
  getFilteredTransactionsByMonth()
    .filter((t) => t.tipe === "keluar")
    .forEach((t) => {
      totalsByCategory[t.kategori] = (totalsByCategory[t.kategori] || 0) + t.nominal;
    });

  const labels = Object.keys(totalsByCategory);
  const values = Object.values(totalsByCategory);

  if (expenseChart) expenseChart.destroy();

  if (labels.length === 0) {
    ctx.classList.add("hidden");
    emptyText.classList.remove("hidden");
    return;
  }

  ctx.classList.remove("hidden");
  emptyText.classList.add("hidden");

  const isDark = document.documentElement.classList.contains("dark");
  expenseChart = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels,
      datasets: [
        {
          data: values,
          backgroundColor: ["#1F5B47", "#C85E3F", "#D2A03A", "#7FA88F", "#4F6D8A", "#B9A98B", "#8E4B3A"],
          borderWidth: 3,
          borderColor: isDark ? "#1D1A16" : "#FFFEFB",
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "68%",
      plugins: {
        legend: {
          position: "bottom",
          labels: {
            color: isDark ? "#CFC7B5" : "#544D40",
            boxWidth: 10,
            font: { size: 11, family: "Instrument Sans" },
          },
        },
      },
    },
  });
};

// --- Render Quick Add Templates ---
const renderQuickTemplates = () => {
  const container = document.getElementById("quick-templates-list");
  if (!state.quickTemplates.length) {
    container.innerHTML = `<span class="text-xs text-slate-400">Belum ada template. Klik "Tambah" untuk membuat pintasan 1-klik.</span>`;
    return;
  }

  container.innerHTML = state.quickTemplates
    .map((tpl) => {
      const sign = tpl.tipe === "masuk" ? "+" : "-";
      const color = tpl.tipe === "masuk" ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400";
      return `
        <div class="inline-flex items-center rounded-full border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/70 overflow-hidden">
          <button onclick="useQuickTemplate(${tpl.id})" class="px-3 py-1.5 text-xs font-semibold hover:bg-slate-100 dark:hover:bg-slate-800 transition flex items-center gap-1.5">
            <span>${escapeHtml(tpl.nama)}</span>
            <span class="${color}">${sign}${formatRupiah(tpl.nominal)}</span>
          </button>
          <button onclick="deleteQuickTemplate(${tpl.id})" class="px-2 py-1.5 text-slate-400 hover:text-rose-500 border-l border-slate-200 dark:border-slate-700 transition" title="Hapus Template">
            <i data-lucide="x" class="w-3 h-3"></i>
          </button>
        </div>
      `;
    })
    .join("");

  lucide.createIcons();
};

// --- Render Transactions ---
const createTxHtml = (t) => {
  const isMasuk = t.tipe === "masuk";
  const sign = isMasuk ? "+" : "-";
  const amountColor = isMasuk ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400";
  const iconBg = isMasuk ? "bg-emerald-50 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400" : "bg-rose-50 text-rose-600 dark:bg-rose-500/10 dark:text-rose-400";
  const iconName = isMasuk ? "arrow-down-left" : "arrow-up-right";
  const note = t.catatan ? ` • ${escapeHtml(t.catatan)}` : "";

  return `
    <li class="flex items-center justify-between p-2.5 rounded-xl hover:bg-slate-100/70 dark:hover:bg-slate-800/60 transition gap-3">
      <div class="flex items-center gap-3 min-w-0">
        <div class="w-10 h-10 rounded-full ${iconBg} flex items-center justify-center shrink-0">
          <i data-lucide="${iconName}" class="w-4 h-4"></i>
        </div>
        <div class="min-w-0">
          <div class="font-semibold text-sm truncate">${escapeHtml(t.kategori)}</div>
          <div class="text-xs text-slate-500 dark:text-slate-400 truncate">${escapeHtml(t.tanggal)}${note}</div>
        </div>
      </div>
      <div class="flex items-center gap-1.5 sm:gap-2 shrink-0">
        <span class="font-bold text-sm mr-1 ${amountColor}">${sign}${formatRupiah(t.nominal)}</span>
        <button onclick="openEditTransactionModal(${t.id})" class="p-1.5 text-slate-400 hover:text-brand-600 rounded-lg transition" title="Edit">
          <i data-lucide="pencil" class="w-4 h-4"></i>
        </button>
        <button onclick="deleteTransaction(${t.id})" class="p-1.5 text-slate-400 hover:text-rose-500 rounded-lg transition" title="Hapus">
          <i data-lucide="trash-2" class="w-4 h-4"></i>
        </button>
      </div>
    </li>
  `;
};

const renderTransactions = () => {
  const recentList = document.getElementById("recent-list");
  const recent = getFilteredTransactionsByMonth().slice(0, 5);
  recentList.innerHTML = recent.length
    ? recent.map(createTxHtml).join("")
    : `<li class="text-center text-xs text-slate-400 py-8">Belum ada transaksi di periode ini.</li>`;

  const filter = document.getElementById("filter-tipe").value;
  const query = document.getElementById("search-input").value.toLowerCase().trim();
  const filtered = state.transactions.filter((t) => {
    const matchType = filter === "semua" || t.tipe === filter;
    const matchQuery =
      !query ||
      t.kategori.toLowerCase().includes(query) ||
      (t.catatan && t.catatan.toLowerCase().includes(query));
    return matchType && matchQuery;
  });

  const fullList = document.getElementById("transaction-list");
  fullList.innerHTML = filtered.length
    ? filtered.map(createTxHtml).join("")
    : `<li class="text-center text-xs text-slate-400 py-8">Tidak ada transaksi yang cocok.</li>`;

  lucide.createIcons();
};

// --- Render Goals ---
const renderGoals = () => {
  const container = document.getElementById("goals-list");
  if (!state.goals.length) {
    container.innerHTML = `<div class="md:col-span-2 rounded-2xl p-10 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-center text-sm text-slate-400">Belum ada target tabungan. Klik "Target Baru" untuk memulai!</div>`;
    return;
  }

  container.innerHTML = state.goals
    .map((g) => {
      const persen = Math.min(Math.round((g.terkumpul / g.target) * 100), 100);
      const selesai = g.terkumpul >= g.target;
      return `
        <div class="rounded-2xl p-5 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-sm flex flex-col justify-between gap-4">
          <div>
            <div class="flex items-start justify-between gap-2 mb-2">
              <h4 class="font-bold text-base">${escapeHtml(g.nama)}</h4>
              <span class="px-2.5 py-0.5 rounded-full text-xs font-bold ${selesai ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/20 dark:text-emerald-300" : "bg-brand-50 text-brand-600 dark:bg-brand-400/20 dark:text-brand-300"}">
                ${selesai ? "Tercapai!" : `${persen}%`}
              </span>
            </div>
            <p class="text-xs text-slate-500 dark:text-slate-400 mb-3">
              Terkumpul <strong class="text-slate-800 dark:text-slate-200">${formatRupiah(g.terkumpul)}</strong> dari ${formatRupiah(g.target)}
            </p>
            <div class="w-full h-2.5 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
              <div class="h-full ${selesai ? "bg-emerald-500" : "bg-brand-600 dark:bg-brand-500"} rounded-full transition-all duration-300" style="width: ${persen}%;"></div>
            </div>
          </div>
          <div class="flex items-center justify-between pt-2 border-t border-slate-100 dark:border-slate-800">
            <button onclick="openSetorModal(${g.id})" class="text-xs font-semibold text-brand-600 dark:text-brand-300 hover:underline flex items-center gap-1">
              <i data-lucide="plus-circle" class="w-3.5 h-3.5"></i> Tambah Tabungan
            </button>
            <button onclick="deleteGoal(${g.id})" class="text-xs font-semibold text-rose-500 hover:underline">Hapus</button>
          </div>
        </div>
      `;
    })
    .join("");

  lucide.createIcons();
};

// --- Render Debts (Hutang / Piutang) ---
const renderDebts = () => {
  let totalPiutang = 0;
  let totalHutang = 0;
  state.debts.forEach((d) => {
    if (d.status === "belum") {
      if (d.tipe === "piutang") totalPiutang += d.nominal;
      else totalHutang += d.nominal;
    }
  });

  document.getElementById("total-piutang").textContent = formatRupiah(totalPiutang);
  document.getElementById("total-hutang").textContent = formatRupiah(totalHutang);

  const list = document.getElementById("debts-list");
  if (!state.debts.length) {
    list.innerHTML = `<li class="text-center text-xs text-slate-400 py-8">Belum ada catatan hutang atau piutang.</li>`;
    return;
  }

  list.innerHTML = state.debts
    .map((d) => {
      const isPiutang = d.tipe === "piutang";
      const isLunas = d.status === "lunas";
      const typeLabel = isPiutang ? "Piutang" : "Hutang";
      const typeColor = isPiutang ? "text-emerald-600 dark:text-emerald-400" : "text-rose-600 dark:text-rose-400";
      const note = d.catatan ? ` • ${escapeHtml(d.catatan)}` : "";

      return `
        <li class="flex flex-wrap items-center justify-between p-3.5 rounded-xl border border-slate-100 dark:border-slate-800 ${isLunas ? "opacity-60" : ""} gap-3">
          <div class="min-w-0">
            <div class="flex items-center gap-2">
              <span class="font-bold text-sm">${escapeHtml(d.nama_orang)}</span>
              <span class="px-2 py-0.5 rounded-full text-[11px] font-semibold ${isLunas ? "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400" : "bg-amber-100 text-amber-700 dark:bg-amber-500/20 dark:text-amber-300"}">
                ${isLunas ? "Lunas" : "Belum Lunas"}
              </span>
            </div>
            <div class="text-xs text-slate-500 dark:text-slate-400 mt-0.5">${typeLabel}${note}</div>
          </div>
          <div class="flex items-center gap-2.5">
            <span class="font-bold text-sm ${typeColor}">${formatRupiah(d.nominal)}</span>
            ${!isLunas ? `<button data-nama="${escapeHtml(d.nama_orang)}" onclick="settleDebt(${d.id}, this.dataset.nama, '${d.tipe}')" class="px-2.5 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold transition">Lunas</button>` : ""}
            <button onclick="deleteDebt(${d.id})" class="p-1.5 text-slate-400 hover:text-rose-500 rounded-lg transition" title="Hapus">
              <i data-lucide="trash-2" class="w-4 h-4"></i>
            </button>
          </div>
        </li>
      `;
    })
    .join("");

  lucide.createIcons();
};

const renderAll = () => {
  renderSummary();
  renderChart();
  renderQuickTemplates();
  renderTransactions();
  renderGoals();
  renderDebts();
};

// --- API Actions ---
document.getElementById("month-filter").addEventListener("change", (e) => {
  state.selectedMonth = e.target.value;
  renderSummary();
  renderChart();
  renderTransactions();
});

document.getElementById("form-transaksi").addEventListener("submit", async (e) => {
  e.preventDefault();
  const editId = document.getElementById("edit-tx-id").value;
  const payload = {
    tipe: document.getElementById("tipe").value,
    nominal: Number(document.getElementById("nominal").value),
    kategori: document.getElementById("kategori").value,
    tanggal: document.getElementById("tanggal").value,
    catatan: document.getElementById("catatan").value.trim(),
  };

  const url = editId ? `/api/transactions/${editId}` : "/api/transactions";
  const method = editId ? "PUT" : "POST";

  const res = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (res.ok) {
    closeModal("modal-transaksi");
    e.target.reset();
    document.getElementById("edit-tx-id").value = "";
    document.getElementById("tanggal").value = getTodayDate();
    showToast(editId ? "Transaksi diperbarui" : "Transaksi berhasil disimpan");
    fetchData(true);
  } else {
    showToast("Gagal menyimpan transaksi", "error");
  }
});

window.deleteTransaction = async (id) => {
  if (!confirm("Hapus transaksi ini?")) return;
  const res = await fetch(`/api/transactions/${id}`, { method: "DELETE" });
  if (res.ok) {
    showToast("Transaksi dihapus");
    fetchData(true);
  }
};

// Quick Templates Actions
document.getElementById("form-template").addEventListener("submit", async (e) => {
  e.preventDefault();
  const payload = {
    nama: document.getElementById("tpl-nama").value.trim(),
    tipe: document.getElementById("tpl-tipe").value,
    nominal: Number(document.getElementById("tpl-nominal").value),
    kategori: document.getElementById("tpl-kategori").value,
  };
  const res = await fetch("/api/templates", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (res.ok) {
    closeModal("modal-template");
    e.target.reset();
    syncTplCategories();
    showToast("Template cepat ditambahkan");
    fetchData(true);
  }
});

window.useQuickTemplate = async (id) => {
  const tpl = state.quickTemplates.find((t) => t.id === id);
  if (!tpl) return;
  const res = await fetch("/api/transactions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      tipe: tpl.tipe,
      nominal: tpl.nominal,
      kategori: tpl.kategori,
      tanggal: getTodayDate(),
      catatan: tpl.nama,
    }),
  });
  if (res.ok) {
    showToast(`Tercatat: ${tpl.nama} (${formatRupiah(tpl.nominal)})`);
    fetchData(true);
  }
};

window.deleteQuickTemplate = async (id) => {
  if (!confirm("Hapus template ini?")) return;
  const res = await fetch(`/api/templates/${id}`, { method: "DELETE" });
  if (res.ok) {
    showToast("Template dihapus");
    fetchData(true);
  }
};

// Debts Actions
document.getElementById("form-hutang").addEventListener("submit", async (e) => {
  e.preventDefault();
  const payload = {
    tipe: document.getElementById("debt-tipe").value,
    nama_orang: document.getElementById("debt-nama").value.trim(),
    nominal: Number(document.getElementById("debt-nominal").value),
    catatan: document.getElementById("debt-catatan").value.trim(),
  };
  const res = await fetch("/api/debts", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (res.ok) {
    closeModal("modal-hutang");
    e.target.reset();
    showToast("Catatan kasbon disimpan");
    fetchData(true);
  }
});

window.settleDebt = async (id, nama, tipe) => {
  const msg = tipe === "piutang"
    ? `Tandai piutang ${nama} LUNAS dan otomatis tambahkan ke Pemasukan saldo? (Klik Cancel jika ingin lunas tanpa ubah saldo)`
    : `Tandai hutang ke ${nama} LUNAS dan otomatis potong dari Pengeluaran saldo? (Klik Cancel jika ingin lunas tanpa ubah saldo)`;
  const catat_transaksi = confirm(msg);
  const res = await fetch(`/api/debts/${id}/settle`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ catat_transaksi, tanggal: getTodayDate() }),
  });
  if (res.ok) {
    showToast(catat_transaksi ? "Lunas & saldo diperbarui!" : "Ditandai lunas");
    fetchData(true);
  }
};

window.deleteDebt = async (id) => {
  if (!confirm("Hapus catatan hutang/piutang ini?")) return;
  const res = await fetch(`/api/debts/${id}`, { method: "DELETE" });
  if (res.ok) {
    showToast("Catatan dihapus");
    fetchData(true);
  }
};

// Goals Actions
document.getElementById("form-target").addEventListener("submit", async (e) => {
  e.preventDefault();
  const payload = {
    nama: document.getElementById("target-nama").value.trim(),
    target: Number(document.getElementById("target-nominal").value),
  };

  const res = await fetch("/api/goals", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (res.ok) {
    closeModal("modal-target");
    e.target.reset();
    showToast("Target tabungan dibuat");
    fetchData(true);
  }
});

document.getElementById("form-setor").addEventListener("submit", async (e) => {
  e.preventDefault();
  const goalId = document.getElementById("setor-goal-id").value;
  const jumlah = Number(document.getElementById("setor-nominal").value);
  const potong_saldo = document.getElementById("setor-potong-saldo").checked;

  const res = await fetch(`/api/goals/${goalId}/add`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jumlah, potong_saldo, tanggal: getTodayDate() }),
  });

  if (res.ok) {
    closeModal("modal-setor");
    showToast(potong_saldo ? "Tabungan ditambah & saldo dipotong" : "Tabungan ditambahkan!");
    fetchData(true);
  } else {
    showToast("Gagal menambah tabungan", "error");
  }
});

window.deleteGoal = async (id) => {
  if (!confirm("Hapus target tabungan ini?")) return;
  const res = await fetch(`/api/goals/${id}`, { method: "DELETE" });
  if (res.ok) {
    showToast("Target dihapus");
    fetchData(true);
  }
};

// Limit & Account Actions
document.getElementById("form-limit").addEventListener("submit", async (e) => {
  e.preventDefault();
  const daily_limit = Number(document.getElementById("input-daily-limit").value);
  const res = await fetch("/api/settings/daily-limit", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ daily_limit }),
  });

  if (res.ok) {
    closeModal("modal-limit");
    showToast("Batas harian diperbarui");
    fetchData(true);
  }
});

document.getElementById("form-profile").addEventListener("submit", async (e) => {
  e.preventDefault();
  const nama = document.getElementById("input-profile-nama").value.trim();
  const res = await fetch("/api/account/profile", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ nama }),
  });
  const data = await res.json();
  if (res.ok) {
    showToast("Nama panggilan diperbarui");
    fetchData(true);
  } else {
    showToast(data.error || "Gagal memperbarui nama", "error");
  }
});

document.getElementById("form-password").addEventListener("submit", async (e) => {
  e.preventDefault();
  const old_password = document.getElementById("input-old-pw").value;
  const new_password = document.getElementById("input-new-pw").value;
  const res = await fetch("/api/account/password", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ old_password, new_password }),
  });
  const data = await res.json();
  if (res.ok) {
    e.target.reset();
    showToast("Password berhasil diubah");
  } else {
    showToast(data.error || "Gagal mengubah password", "error");
  }
});

document.getElementById("filter-tipe").addEventListener("change", renderTransactions);
document.getElementById("search-input").addEventListener("input", renderTransactions);

window.logoutUser = async () => {
  if (!confirm("Keluar dari akun ini?")) return;
  await fetch("/api/logout", { method: "POST" });
  window.location.href = "/auth";
};

// --- Init & Real-Time Polling (3 detik) ---
initTheme();
document.getElementById("tanggal").value = getTodayDate();
lucide.createIcons();
fetchData(true);

setInterval(() => {
  if (!document.hidden) {
    fetchData(false);
  }
}, 3000);

// Ganti tipe -> daftar kategori ikut berganti
document.getElementById("tipe").addEventListener("change", () => syncTxCategories());
document.getElementById("tpl-tipe").addEventListener("change", () => syncTplCategories());
syncTxCategories();
syncTplCategories();
