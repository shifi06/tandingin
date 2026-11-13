/* Tanding.in v1.0 - frontend (HTML + Bootstrap + vanilla JS) */
const $app = document.getElementById('app');
let me = null;

let roleRefreshPromise = null;

async function refreshSessionRole() {
  if (!roleRefreshPromise) {
    roleRefreshPromise = (async () => {
      try {
        const response = await fetch('/api/auth/me', {
          credentials: 'same-origin',
          cache: 'no-store',
        });
        if (!response.ok) return false;
        const latest = await response.json();
        if (!latest) {
          me = null;
          location.hash = '#/login';
          return true;
        }
        const changed = !me || latest.id_user !== me.id_user || latest.role !== me.role;
        if (!changed) return false;

        me = latest;
        renderNav();
        const currentRoute = location.hash.split('/')[1] || '';
        const requiredRole = ROLE_ONLY[currentRoute];
        if (requiredRole && me.role !== requiredRole) location.hash = '#/turnamen';
        toast('Role akun berubah. Menu dan hak akses telah diperbarui.', 'warning');
        return true;
      } catch {
        return false;
      }
    })().finally(() => { roleRefreshPromise = null; });
  }
  return roleRefreshPromise;
}

const esc = s => String(s ?? '').replace(/[&<>"']/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmtDT = s => s ? new Date(s).toLocaleString('id-ID', { dateStyle: 'medium', timeStyle: 'short' }) : '-';
const fmtD = s => s ? new Date(s).toLocaleDateString('id-ID', { dateStyle: 'long' }) : '-';
const ROLE_LABEL = { super_admin: 'Super Admin', panitia: 'Panitia', kapten: 'Kapten Tim' };

async function api(path, opts = {}) {
  const o = { credentials: 'same-origin', ...opts };
  if (o.body && !(o.body instanceof FormData)) {
    o.headers = { 'Content-Type': 'application/json' };
    o.body = JSON.stringify(o.body);
  }
  const r = await fetch('/api' + path, o);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    // The role can be changed by Super Admin while this tab is still open.
    // The frontend's cached "me" may then disagree with the role checked by Flask.
    if (r.status === 403 && data.error === 'Anda tidak punya hak akses untuk aksi ini.') {
      const refreshed = await refreshSessionRole();
      if (refreshed) {
        const err = new Error('Hak akses akun berubah. Tampilan sudah disesuaikan dengan role terbaru.');
        err.silent = true; // refreshSessionRole already displays one notification
        throw err;
      }
    }
    if (r.status === 401 && me) { me = null; location.hash = '#/login'; }
    throw new Error(data.error || 'Terjadi kesalahan.');
  }
  return data;
}

function toast(msg, type = 'success') {
  const el = document.createElement('div');
  el.className = `toast align-items-center text-bg-${type} border-0`;
  el.innerHTML = `<div class="d-flex"><div class="toast-body">${esc(msg)}</div>
    <button class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button></div>`;
  document.getElementById('toasts').appendChild(el);
  const t = new bootstrap.Toast(el, { delay: 3500 });
  el.addEventListener('hidden.bs.toast', () => el.remove());
  t.show();
}
const fail = e => { if (!e.silent) toast(e.message, 'danger'); };

/* ---------- modal ---------- */
const modalEl = document.getElementById('modal');
const modal = new bootstrap.Modal(modalEl);
let modalHandler = null;
function showModal(title, html, onSubmit, okLabel = 'Simpan') {
  document.getElementById('modalTitle').textContent = title;
  document.getElementById('modalBody').innerHTML = html;
  document.getElementById('modalOk').textContent = okLabel;
  modalHandler = onSubmit;
  modal.show();
}
document.getElementById('modalForm').addEventListener('submit', async e => {
  e.preventDefault();
  try { await modalHandler(new FormData(e.target)); modal.hide(); } catch (err) { fail(err); }
});

/* ---------- komponen kecil ---------- */
const badge = (s) => {
  const cls = { aktif: 'success', selesai: 'secondary', Menunggu: 'warning text-dark',
    Diproses: 'info text-dark', Selesai: 'success', Disetujui: 'success', Ditolak: 'danger' }[s] || 'light text-dark';
  return `<span class="badge text-bg-${cls}">${esc(s)}</span>`;
};
const timLabel = t => `${t.logo_url ? `<img class="logo" src="${esc(t.logo_url)}">` : ''}${esc(t.nama_tim)}`;
const card = (title, inner, extra = '') =>
  `<div class="card mb-4"><div class="card-body"><div class="d-flex justify-content-between align-items-center mb-3">
   <h5 class="card-title mb-0">${title}</h5>${extra}</div>${inner}</div></div>`;
const empty = msg => `<p class="text-muted mb-0">${msg}</p>`;
const table = (heads, rows) => rows.length
  ? `<div class="table-responsive"><table class="table table-hover align-middle mb-0"><thead><tr>${heads.map(h => `<th>${h}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`
  : '';

function hasilCell(j) {
  const h = j.hasil;
  if (!h) return '<span class="text-muted">Belum ada hasil resmi</span>';
  const evidence = h.foto_bukti_url
    ? `<a href="${esc(h.foto_bukti_url)}" target="_blank" rel="noopener noreferrer"><img class="bukti-thumb" src="${esc(h.foto_bukti_url)}"></a>`
    : '';
  return `<div class="d-flex gap-2 align-items-center">${evidence}
    <div>${badge(h.status_validasi)}<div class="small">Menang: <b>${esc(h.nama_pemenang)}</b></div>
    ${h.catatan_validasi ? `<div class="small text-danger">Catatan: ${esc(h.catatan_validasi)}</div>` : ''}</div></div>`;
}

function jadwalRows(list) {
  return list.map(j => `<tr>
    <td>${esc(j.turnamen.nama_turnamen)}</td>
    <td>${timLabel(j.tim_a)}<span class="vs">VS</span>${timLabel(j.tim_b)}</td>
    <td>${fmtDT(j.jadwal_main)}</td><td>${badge(j.status_match)}</td><td>${hasilCell(j)}</td>
    <td>${j.bisa_unggah ? `<button class="btn btn-sm btn-brand" data-act="unggah" data-id="${j.id_jadwal}">Unggah bukti</button>` : ''}</td>
  </tr>`);
}
const jadwalTable = list => list.length
  ? table(['Turnamen', 'Pertandingan', 'Waktu', 'Status', 'Bukti hasil', ''], jadwalRows(list))
  : empty('Belum ada jadwal pertandingan.');

/* ---------- navigasi ---------- */
function renderNav() {
  const links = [['#/turnamen', 'Turnamen'], ['#/jadwal', 'Jadwal']];
  if (me?.role === 'kapten') links.push(['#/tim', 'Tim Saya']);
  if (me?.role === 'panitia') links.push(['#/kelola', 'Kelola Turnamen'], ['#/validasi', 'Validasi Hasil']);
  if (me?.role === 'super_admin') links.push(['#/admin', 'Pengguna']);
  const cur = location.hash.split('/').slice(0, 2).join('/');
  document.getElementById('navLinks').innerHTML = links.map(([h, l]) =>
    `<li class="nav-item"><a class="nav-link ${cur === h ? 'active' : ''}" href="${h}">${l}</a></li>`).join('');
  document.getElementById('navUser').innerHTML = me
    ? `<span class="small">${esc(me.nama)} <span class="badge text-bg-light">${ROLE_LABEL[me.role]}</span></span>
       <button class="btn btn-sm btn-outline-light" data-act="logout">Keluar</button>`
    : `<a class="btn btn-sm btn-outline-light me-2" href="#/login">Masuk</a>
       <a class="btn btn-sm btn-light" href="#/register">Daftar</a>`;
}

const routes = {
  login: viewLogin, register: viewRegister, turnamen: viewTurnamen, jadwal: viewJadwal,
  tim: viewTim, kelola: viewKelola, validasi: viewValidasi, admin: viewAdmin,
};
const ROLE_ONLY = { tim: 'kapten', kelola: 'panitia', validasi: 'panitia', admin: 'super_admin' };

async function route() {
  const [, name = '', arg] = location.hash.split('/');
  if (!me && ROLE_ONLY[name]) { location.hash = '#/login'; return; }
  if (me && ['login', 'register', ''].includes(name)) { location.hash = '#/turnamen'; return; }
  if (ROLE_ONLY[name] && me.role !== ROLE_ONLY[name]) { toast('Anda tidak punya akses ke halaman itu.', 'danger'); location.hash = '#/turnamen'; return; }
  renderNav();
  try { await (routes[name] || viewTurnamen)(arg); } catch (e) { $app.innerHTML = `<div class="alert alert-danger">${esc(e.message)}</div>`; }
}
window.addEventListener('hashchange', route);

/* ---------- auth ---------- */
function viewLogin() {
  $app.innerHTML = `<div class="row justify-content-center"><div class="col-md-5">
    <div class="text-center mb-4"><h2 class="fw-bold">Tanding<span class="text-accent">.in</span></h2>
    <p class="text-muted">Manajemen turnamen &amp; pencatatan hasil pertandingan e-sports</p></div>
    ${card('Masuk', `<form data-form="login">
      <div class="mb-3"><label class="form-label">Email</label><input name="email" type="email" class="form-control" required></div>
      <div class="mb-3"><label class="form-label">Password</label><input name="password" type="password" class="form-control" required></div>
      <button class="btn btn-brand w-100">Masuk</button></form>
      <p class="small text-center mt-3 mb-0">Kapten tim baru? <a href="#/register">Daftar di sini</a></p>`)}
  </div></div>`;
}
function viewRegister() {
  $app.innerHTML = `<div class="row justify-content-center"><div class="col-md-5">
    ${card('Daftar sebagai Kapten Tim', `<form data-form="register">
      <div class="mb-3"><label class="form-label">Nama</label><input name="nama" class="form-control" required></div>
      <div class="mb-3"><label class="form-label">Email</label><input name="email" type="email" class="form-control" required></div>
      <div class="mb-3"><label class="form-label">Password (min. 8 karakter)</label><input name="password" type="password" minlength="8" class="form-control" required></div>
      <button class="btn btn-brand w-100">Daftar</button></form>
      <p class="small text-center mt-3 mb-0">Sudah punya akun? <a href="#/login">Masuk</a></p>
      <p class="small text-muted text-center mt-2 mb-0">Akun Panitia dibuat oleh Super Admin.</p>`)}
  </div></div>`;
}

/* ---------- turnamen & jadwal (semua role) ---------- */
async function viewTurnamen(id) {
  if (id) return viewTurnamenDetail(id);
  const list = await api('/turnamen');
  const isK = me?.role === 'kapten';
  let hint = '';
  if (isK && !me.id_tim) hint = `<div class="alert alert-info">Buat <a href="#/tim">profil tim</a> dulu untuk bisa mendaftar ke turnamen.</div>`;
  const rows = list.map(t => {
    let action = '';
    if (isK && me.id_tim && t.status === 'aktif') {
      action = t.saya_terdaftar
        ? '<span class="badge text-bg-success">Terdaftar</span>'
        : `<button class="btn btn-sm btn-brand" data-act="daftar" data-id="${t.id_turnamen}">Daftar</button>`;
    } else if (!me) {
      action = `<a class="btn btn-sm btn-outline-dark" href="#/login">Masuk untuk daftar</a>`;
    } else if (isK && !me.id_tim) {
      action = `<a class="btn btn-sm btn-outline-dark" href="#/tim">Buat profil tim</a>`;
    }
    return `<tr>
      <td><b>${esc(t.nama_turnamen)}</b></td><td>${fmtD(t.tanggal_mulai)}</td><td>${badge(t.status)}</td>
      <td>${esc(t.panitia)}</td><td>${t.jumlah_tim}</td>
      <td><a class="btn btn-sm btn-outline-dark" href="#/turnamen/${t.id_turnamen}">Lihat room</a> ${action}</td>
    </tr>`;
  });
  $app.innerHTML = hint + card('Daftar Turnamen',
    rows.length ? table(['Turnamen', 'Mulai', 'Status', 'Penyelenggara', 'Tim', 'Aksi'], rows) : empty('Belum ada turnamen.'));
}

async function viewTurnamenDetail(id) {
  const [t, peserta, jadwal] = await Promise.all([
    api('/turnamen/' + id), api(`/turnamen/${id}/peserta`), api(`/jadwal?turnamen_id=${id}`)
  ]);
  const action = !me
    ? '<a class="btn btn-sm btn-brand" href="#/login">Masuk untuk mendaftar</a>'
    : me.role === 'kapten' && !me.id_tim
      ? '<a class="btn btn-sm btn-brand" href="#/tim">Buat profil tim</a>' : '';
  const teams = peserta.length
    ? table(['Nama Tim', 'Kapten'], peserta.map(p => `<tr><td>${timLabel(p)}</td><td>${esc(p.kapten)}</td></tr>`))
    : empty('Belum ada tim yang terdaftar.');
  $app.innerHTML = `<a href="#/turnamen" class="small">&larr; Kembali ke daftar turnamen</a>
    <div class="d-flex justify-content-between align-items-center my-3 flex-wrap gap-2">
      <div><h3 class="mb-1">${esc(t.nama_turnamen)}</h3><div class="text-muted small">Mulai ${fmtD(t.tanggal_mulai)} · ${badge(t.status)}</div></div>
      ${action}
    </div>`
    + card(`Tim Peserta (${peserta.length})`, teams)
    + card('Jadwal dan Hasil Pertandingan', jadwalTable(jadwal));
}

async function viewJadwal() {
  const [ts, list] = await Promise.all([api('/turnamen'), api('/jadwal')]);
  $app.innerHTML = card('Jadwal Pertandingan', `
    <div class="row g-2 mb-3"><div class="col-md-5"><select id="fTurnamen" class="form-select">
      <option value="">Semua turnamen</option>${ts.map(t => `<option value="${t.id_turnamen}">${esc(t.nama_turnamen)}</option>`).join('')}
    </select></div>
    ${me?.role === 'kapten' ? `<div class="col-auto form-check pt-2 ms-2"><input type="checkbox" id="fMine" class="form-check-input">
      <label for="fMine" class="form-check-label">Hanya match tim saya</label></div>` : ''}</div>
    <div id="jadwalBox">${jadwalTable(list)}</div>`);
  const reload = async () => {
    const q = new URLSearchParams();
    if (fTurnamen.value) q.set('turnamen_id', fTurnamen.value);
    if (document.getElementById('fMine')?.checked) q.set('milik_saya', '1');
    document.getElementById('jadwalBox').innerHTML = jadwalTable(await api('/jadwal?' + q));
  };
  fTurnamen.onchange = reload;
  document.getElementById('fMine')?.addEventListener('change', reload);
}

/* ---------- Kapten: tim saya (US-03) ---------- */
async function viewTim() {
  const [tim, ts] = await Promise.all([api('/tim/saya'), api('/turnamen')]);
  me.id_tim = tim ? tim.id_tim : null;
  const aktif = ts.filter(t => t.status === 'aktif');
  if (!tim) {
    $app.innerHTML = card('Buat Profil Tim', `<form data-form="buatTim">
      <div class="mb-3"><label class="form-label">Nama tim</label><input name="nama_tim" class="form-control" required></div>
      <div class="mb-3"><label class="form-label">Logo (opsional, PNG/JPG/WEBP, maks 4 MB)</label>
        <input name="logo" type="file" accept="image/png,image/jpeg,image/webp" class="form-control"></div>
      <div class="mb-3"><label class="form-label">Langsung daftar ke turnamen (opsional)</label>
        <select name="id_turnamen" class="form-select"><option value="">- nanti saja -</option>
        ${aktif.map(t => `<option value="${t.id_turnamen}">${esc(t.nama_turnamen)}</option>`).join('')}</select></div>
      <button class="btn btn-brand">Simpan tim</button></form>`);
    return;
  }
  const rows = aktif.map(t => `<tr><td>${esc(t.nama_turnamen)}</td><td>${fmtD(t.tanggal_mulai)}</td><td>
    ${t.saya_terdaftar ? '<span class="badge text-bg-success">Terdaftar</span>'
      : `<button class="btn btn-sm btn-brand" data-act="daftar" data-id="${t.id_turnamen}">Daftar</button>`}</td></tr>`);
  $app.innerHTML = card('Profil Tim', `<div class="d-flex align-items-center gap-3 mb-3">
      ${tim.logo_url ? `<img src="${esc(tim.logo_url)}" style="width:64px;height:64px;border-radius:12px;object-fit:cover">` : ''}
      <div><h4 class="mb-0">${esc(tim.nama_tim)}</h4><span class="text-muted">Kapten: ${esc(tim.kapten)}</span></div></div>
    <form data-form="editTim" class="row g-2">
      <div class="col-md-5"><input name="nama_tim" class="form-control" value="${esc(tim.nama_tim)}" required></div>
      <div class="col-md-5"><input name="logo" type="file" accept="image/png,image/jpeg,image/webp" class="form-control"></div>
      <div class="col-md-2"><button class="btn btn-outline-dark w-100">Perbarui</button></div></form>`)
    + card('Turnamen Aktif', rows.length ? table(['Turnamen', 'Mulai', ''], rows) : empty('Belum ada turnamen aktif.'));
}

/* ---------- Panitia: kelola turnamen (US-02, US-04) ---------- */
async function viewKelola(id) {
  if (id) return viewKelolaDetail(id);
  const list = await api('/turnamen?milik_saya=1');
  $app.innerHTML = card('Buat Room Turnamen Baru', `<form data-form="buatTurnamen" class="row g-2">
      <div class="col-md-6"><input name="nama_turnamen" class="form-control" placeholder="Nama turnamen" required></div>
      <div class="col-md-4"><input name="tanggal_mulai" type="date" class="form-control" required></div>
      <div class="col-md-2"><button class="btn btn-brand w-100">Buat</button></div></form>`)
    + card('Turnamen Saya', list.length ? table(['Turnamen', 'Mulai', 'Status', 'Tim', ''], list.map(t => `<tr>
      <td><b>${esc(t.nama_turnamen)}</b></td><td>${fmtD(t.tanggal_mulai)}</td><td>${badge(t.status)}</td><td>${t.jumlah_tim}</td>
      <td><a class="btn btn-sm btn-outline-dark" href="#/kelola/${t.id_turnamen}">Kelola</a></td></tr>`))
      : empty('Anda belum membuat turnamen.'));
}

async function viewKelolaDetail(id) {
  const [t, peserta, jadwal] = await Promise.all([
    api('/turnamen/' + id), api(`/tim?turnamen_id=${id}`), api(`/jadwal?turnamen_id=${id}`)]);
  const opts = peserta.map(p => `<option value="${p.id_tim}">${esc(p.nama_tim)}</option>`).join('');
  const aktif = t.status === 'aktif';
  $app.innerHTML = `<a href="#/kelola" class="small">&larr; Kembali</a>
    <div class="d-flex justify-content-between align-items-center my-2">
      <h3 class="mb-0">${esc(t.nama_turnamen)} ${badge(t.status)}</h3>
      <button class="btn btn-sm btn-outline-dark" data-act="statusTurnamen" data-id="${t.id_turnamen}" data-status="${aktif ? 'selesai' : 'aktif'}">
        ${aktif ? 'Tandai selesai' : 'Aktifkan kembali'}</button></div>
    <p class="text-muted">Mulai ${fmtD(t.tanggal_mulai)}</p>`
    + card(`Tim Peserta (${peserta.length})`, peserta.length
      ? `<div class="d-flex flex-wrap gap-3">${peserta.map(p => `<span>${timLabel(p)} <span class="text-muted small">(${esc(p.kapten)})</span></span>`).join('')}</div>`
      : empty('Belum ada tim yang mendaftar.'))
    + (aktif ? card('Buat Jadwal Match', peserta.length < 2 ? empty('Minimal 2 tim terdaftar untuk membuat jadwal.') : `
      <form data-form="buatJadwal" class="row g-2"><input type="hidden" name="id_turnamen" value="${t.id_turnamen}">
        <div class="col-md-3"><select name="id_tim_a" class="form-select" required>${opts}</select></div>
        <div class="col-md-3"><select name="id_tim_b" class="form-select" required>${opts}</select></div>
        <div class="col-md-4"><input name="jadwal_main" type="datetime-local" class="form-control" required></div>
        <div class="col-md-2"><button class="btn btn-brand w-100">Simpan</button></div></form>`) : '')
    + card('Jadwal Turnamen Ini', jadwalTable(jadwal));
  if (peserta.length > 1) { const b = document.querySelector('[name=id_tim_b]'); if (b) b.selectedIndex = 1; }
}

/* ---------- Panitia: validasi hasil (US-06) ---------- */
async function viewValidasi() {
  const list = await api('/hasil');
  const rows = list.map(h => {
    const j = h.jadwal;
    return `<tr><td>${esc(j.turnamen.nama_turnamen)}</td>
      <td>${timLabel(j.tim_a)}<span class="vs">VS</span>${timLabel(j.tim_b)}<div class="small text-muted">${fmtDT(j.jadwal_main)}</div></td>
      <td>${hasilCell({ hasil: h })}<div class="small text-muted">Diunggah ${fmtDT(h.waktu_unggah)}</div></td>
      <td>${h.status_validasi === 'Menunggu' ? `
        <button class="btn btn-sm btn-success me-1" data-act="validasi" data-id="${h.id_hasil}" data-k="setuju">Setujui</button>
        <button class="btn btn-sm btn-outline-danger" data-act="validasi" data-id="${h.id_hasil}" data-k="tolak">Tolak</button>` : ''}</td></tr>`;
  });
  $app.innerHTML = card('Validasi Bukti Hasil Pertandingan',
    rows.length ? table(['Turnamen', 'Pertandingan', 'Bukti', 'Aksi'], rows) : empty('Belum ada bukti hasil yang diunggah.'));
}

/* ---------- Super Admin: pengguna (US-01) ---------- */
async function viewAdmin() {
  const list = await api('/users');
  const sel = (u) => `<select class="form-select form-select-sm" data-role-user="${u.id_user}" ${u.id_user === me.id_user ? 'disabled' : ''}>
    ${Object.entries(ROLE_LABEL).map(([k, l]) => `<option value="${k}" ${u.role === k ? 'selected' : ''}>${l}</option>`).join('')}</select>`;
  $app.innerHTML = card('Tambah Pengguna', `<form data-form="buatUser" class="row g-2">
      <div class="col-md-3"><input name="nama" class="form-control" placeholder="Nama" required></div>
      <div class="col-md-3"><input name="email" type="email" class="form-control" placeholder="Email" required></div>
      <div class="col-md-2"><input name="password" type="password" minlength="8" class="form-control" placeholder="Password" required></div>
      <div class="col-md-2"><select name="role" class="form-select">
        ${Object.entries(ROLE_LABEL).map(([k, l]) => `<option value="${k}" ${k === 'panitia' ? 'selected' : ''}>${l}</option>`).join('')}</select></div>
      <div class="col-md-2"><button class="btn btn-brand w-100">Tambah</button></div></form>`)
    + card('Daftar Pengguna', table(['Nama', 'Email', 'Role'], list.map(u =>
      `<tr><td>${esc(u.nama)}</td><td>${esc(u.email)}</td><td style="max-width:180px">${sel(u)}</td></tr>`)));
}

/* ---------- aksi (event delegation) ---------- */
const formObj = f => Object.fromEntries([...f.entries()].filter(([, v]) => !(v instanceof File)));
const actions = {
  async logout() { await api('/auth/logout', { method: 'POST' }); me = null; renderNav(); location.hash = '#/login'; },
  async daftar({ id }) {
    await api(`/turnamen/${id}/daftar`, { method: 'POST' });
    toast('Tim berhasil didaftarkan ke turnamen.'); route();
  },
  unggah({ id }) {
    showModal('Unggah Screenshot Hasil Pertandingan', `
      <p class="small text-muted">Unggah <b>satu</b> foto skor akhir sebagai bukti kemenangan timmu (PNG/JPG/WEBP, maks 4 MB).</p>
      <input name="foto" type="file" accept="image/png,image/jpeg,image/webp" class="form-control" required>`,
      async fd => { await api(`/jadwal/${id}/hasil`, { method: 'POST', body: fd }); toast('Bukti terkirim, menunggu validasi panitia.'); route(); }, 'Kirim');
  },
  async statusTurnamen({ id, status }) {
    await api('/turnamen/' + id, { method: 'PATCH', body: { status } }); route();
  },
  validasi({ id, k }) {
    if (k === 'setuju') {
      showModal('Setujui hasil?', '<p class="mb-0">Hasil akan tercatat sah dan match ditandai <b>Selesai</b>.</p>',
        async () => { await api(`/hasil/${id}/validasi`, { method: 'PATCH', body: { keputusan: 'setuju' } }); toast('Hasil disetujui.'); route(); }, 'Setujui');
    } else {
      showModal('Tolak hasil', '<label class="form-label">Alasan penolakan (dilihat kapten)</label><input name="catatan" class="form-control" placeholder="mis. screenshot buram">',
        async fd => { await api(`/hasil/${id}/validasi`, { method: 'PATCH', body: { keputusan: 'tolak', catatan: fd.get('catatan') } }); toast('Hasil ditolak; kapten dapat unggah ulang.', 'warning'); route(); }, 'Tolak');
    }
  },
};
document.addEventListener('click', e => {
  const b = e.target.closest('[data-act]');
  if (b) actions[b.dataset.act]?.(b.dataset)?.catch?.(fail);
});

const forms = {
  async login(fd) {
    me = await api('/auth/login', { method: 'POST', body: formObj(fd) }); location.hash = '#/turnamen'; route();
  },
  async register(fd) {
    await api('/auth/register', { method: 'POST', body: formObj(fd) });
    me = await api('/auth/login', { method: 'POST', body: { email: fd.get('email'), password: fd.get('password') } });
    toast('Akun dibuat. Silakan buat profil tim.'); location.hash = '#/tim'; route();
  },
  async buatTim(fd) {
    if (!fd.get('id_turnamen')) fd.delete('id_turnamen');
    if (!fd.get('logo')?.size) fd.delete('logo');
    await api('/tim', { method: 'POST', body: fd }); toast('Profil tim dibuat.'); me.id_tim = true; route();
  },
  async editTim(fd) {
    if (!fd.get('logo')?.size) fd.delete('logo');
    await api('/tim/saya', { method: 'PUT', body: fd }); toast('Profil tim diperbarui.'); route();
  },
  async buatTurnamen(fd) {
    const t = await api('/turnamen', { method: 'POST', body: formObj(fd) });
    toast('Room turnamen dibuat.'); location.hash = '#/kelola/' + t.id_turnamen;
  },
  async buatJadwal(fd) {
    await api('/jadwal', { method: 'POST', body: formObj(fd) }); toast('Jadwal dibuat.'); route();
  },
  async buatUser(fd) {
    await api('/auth/register', { method: 'POST', body: formObj(fd) }); toast('Pengguna ditambahkan.'); route();
  },
};
document.addEventListener('submit', e => {
  const name = e.target.dataset.form;
  if (!name) return;
  e.preventDefault();
  forms[name](new FormData(e.target)).catch(fail);
});
document.addEventListener('change', e => {
  const uid = e.target.dataset.roleUser;
  if (!uid) return;
  api(`/users/${uid}/role`, { method: 'PATCH', body: { role: e.target.value } })
    .then(() => toast('Role diperbarui.')).catch(err => { fail(err); route(); });
});

/* ---------- start ---------- */
(async () => {
  try { me = await api('/auth/me'); } catch { me = null; }
  if (!location.hash) location.hash = '#/turnamen';
  route();
})();
