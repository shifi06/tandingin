# Tanding.in

Platform manajemen turnamen esports untuk mengelola turnamen, tim peserta, jadwal pertandingan, dan validasi hasil pertandingan.

**Release candidate:** `1.2.3`  
**Status:** Source package siap untuk validasi integrasi; belum terhubung ke layanan cloud dan belum dideploy.

## Teknologi

- **Frontend:** HTML, CSS, JavaScript, Bootstrap 5
- **Backend:** Python 3.14, Flask
- **Data access:** Flask-SQLAlchemy / SQLAlchemy
- **Database production:** PostgreSQL
- **Schema migration:** Flask-Migrate / Alembic
- **File storage production:** Vercel Blob Private
- **Hosting target:** Vercel Functions

## Fitur aplikasi

- Autentikasi pengguna berbasis session.
- Tiga role: `super_admin`, `panitia`, dan `kapten`.
- Pengelolaan turnamen oleh panitia.
- Pengelolaan tim dan pendaftaran ke turnamen.
- Penjadwalan dan validasi hasil pertandingan.
- Unggah logo tim dan bukti pertandingan.
- Akses file privat melalui endpoint aplikasi dengan pemeriksaan sesi dan otorisasi.

## Struktur repository

```text
.
├── .github/workflows/ci.yml   # Automated CI
├── docs/                      # Project, QA, dan deployment documentation
├── migrations/                # Alembic migration history
├── public/                    # Static frontend served by Vercel
├── scripts/                   # One-time operational / migration scripts
├── tests/                     # Unit and integration tests
├── app.py                     # Flask application entry point
├── models.py                  # SQLAlchemy models
├── storage.py                 # Local and Vercel Blob storage adapters
├── alembic.ini                # Migration configuration
├── requirements.txt           # Python dependencies
├── vercel.json                # Vercel routing and response headers
└── README.md
```

## Persyaratan lokal

- Python 3.14 (lihat `.python-version`)
- pip
- Node.js hanya diperlukan untuk memeriksa sintaks JavaScript

### Linux / WSL / macOS

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
```

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` dan ganti `SECRET_KEY`, `ADMIN_EMAIL`, serta `ADMIN_PASSWORD` dengan nilai lokal milikmu. Jangan commit `.env` atau kredensial.

### Inisialisasi database lokal

Konfigurasi `.env.example` menggunakan SQLite dan local private storage untuk development. Jalankan:

```bash
flask --app app init-db
python app.py
```

Aplikasi lokal tersedia di `http://127.0.0.1:5000`.

Data demo bersifat opsional:

```bash
flask --app app seed-demo
```

Akun demo menggunakan password yang hanya ditujukan untuk development. Jangan gunakan akun atau password demo di production.

## Pengujian

Jalankan seluruh test:

```bash
python -m unittest discover -s tests -v
```

Pemeriksaan tambahan:

```bash
python -m compileall -q app.py models.py storage.py migrations scripts tests
node --check public/js/app.js
```

GitHub Actions menjalankan automated tests, audit dependency (`pip-audit`), kompilasi Python, dan pemeriksaan sintaks JavaScript pada push atau pull request ke `main`.

**Hasil test terakhir yang dilaporkan pemilik project:** 10/10 test lulus di WSL / Python 3.14 (2,557 detik). Hasil tersebut belum mencakup pengujian koneksi PostgreSQL atau operasi Vercel Blob sungguhan. Rincian ada di [`docs/TEST_REPORT.md`](docs/TEST_REPORT.md).

## Deployment

Tanding.in dirancang sebagai satu Vercel project: static frontend di `public/` dan Flask API pada root `app.py`.

Layanan production yang diperlukan:

1. PostgreSQL khusus Tanding.in (misalnya Neon melalui Vercel Marketplace).
2. Vercel Blob Store yang dibuat dengan access mode **Private**.
3. Environment variables untuk `SECRET_KEY`, koneksi PostgreSQL, storage backend, dan bootstrap admin satu kali.

Jalankan schema migration sebelum aplikasi menerima traffic. Jangan aktifkan `AUTO_INIT_DB` pada production. Ikuti [Deployment Runbook](docs/DEPLOYMENT_RUNBOOK.md) untuk provisioning, migration, smoke test, dan rollback.

## Keamanan dan batasan operasional

- Jangan menambahkan `.env`, token, password, database dump, atau file bukti pertandingan ke repository.
- Private Blob harus dibuat dalam mode **Private** sejak awal.
- File privat harus diakses melalui endpoint aplikasi yang memeriksa session dan hak akses.
- Upload dibatasi maksimal 4 MB per file untuk menjaga request/response tetap di bawah limit Vercel Functions.
- Gunakan database dan Blob store terpisah untuk Tanding.in; jangan memakai resource OLION.
- Vercel Hobby ditujukan untuk penggunaan personal/non-komersial. Tinjau ketentuan plan sebelum penggunaan komersial.

## Dokumentasi tambahan

- [Deployment Runbook](docs/DEPLOYMENT_RUNBOOK.md)
- [Project Status & Acceptance Gates](docs/PROJECT_STATUS.md)
- [Test Report](docs/TEST_REPORT.md)
- [Changelog](CHANGELOG.md)
