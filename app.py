"""Tanding.in v1.1 - Platform manajemen turnamen & pencatatan hasil e-sports.

Jalankan:  python app.py      (atau: flask --app app run)
"""
import os
import re
import secrets
from datetime import date, datetime, timedelta
from functools import wraps
from io import BytesIO
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, current_app, jsonify, request, send_file, send_from_directory, session
from flask_migrate import Migrate
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool

from models import (ALL_ROLES, MATCH_DIPROSES, MATCH_MENUNGGU, MATCH_SELESAI, ROLE_ADMIN,
                    ROLE_KAPTEN, ROLE_PANITIA, TURNAMEN_AKTIF, TURNAMEN_SELESAI, VALID_MENUNGGU,
                    VALID_SETUJU, VALID_TOLAK, HasilMatch, JadwalMatch, PendaftaranTurnamen,
                    Role, TimEsports, Turnamen, User, db, utcnow_naive)
from storage import decode_file_token, get_storage

load_dotenv()

ALLOWED_EXT = {"png", "jpg", "jpeg", "webp"}


class ApiError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message, self.status = message, status


def _database_url(value):
    """Normalize common provider URLs to the psycopg 3 SQLAlchemy dialect."""
    if not value:
        return "sqlite:///tandingin.db"
    if value.startswith("postgres://"):
        return "postgresql+psycopg://" + value[len("postgres://"):]
    if value.startswith("postgresql://"):
        return "postgresql+psycopg://" + value[len("postgresql://"):]
    return value


def _as_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def create_app(config=None):
    is_vercel = os.environ.get("VERCEL") == "1"
    is_production = is_vercel or os.environ.get("APP_ENV", "").lower() == "production"
    secret_key = os.environ.get("SECRET_KEY")
    if is_production and not secret_key:
        raise RuntimeError("SECRET_KEY wajib diatur sebelum menjalankan Tanding.in di production.")

    database_url = os.environ.get("DATABASE_URL")
    if _as_bool(os.environ.get("TANDINGIN_DB_MIGRATION")):
        database_url = (os.environ.get("MIGRATION_DATABASE_URL")
                        or os.environ.get("DATABASE_URL_UNPOOLED")
                        or database_url)

    app = Flask(__name__, static_folder=None)
    app.config.update(
        SECRET_KEY=secret_key or secrets.token_urlsafe(48),
        SQLALCHEMY_DATABASE_URI=_database_url(database_url),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={
            "pool_pre_ping": True,
            "pool_recycle": 300,
            # Vercel Functions can scale horizontally; avoid per-instance pools
            # multiplying the database connection count.
            **({"poolclass": NullPool} if is_vercel else {}),
        },
        # Vercel Functions cap request bodies at 4.5 MB including multipart overhead.
        MAX_CONTENT_LENGTH=4 * 1024 * 1024 + 128 * 1024,
        MAX_UPLOAD_BYTES=4 * 1024 * 1024,
        SESSION_COOKIE_NAME="tandingin_session",
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=is_production,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
        SESSION_REFRESH_EACH_REQUEST=False,
        ADMIN_EMAIL=os.environ.get("ADMIN_EMAIL"),
        ADMIN_PASSWORD=os.environ.get("ADMIN_PASSWORD"),
        PUBLIC_FOLDER=os.path.join(os.path.dirname(__file__), "public"),
        UPLOAD_FOLDER=os.path.join(app.instance_path, "uploads"),
        STORAGE_BACKEND=os.environ.get("STORAGE_BACKEND", "vercel_blob" if is_production else "local"),
        AUTO_INIT_DB=_as_bool(os.environ.get("AUTO_INIT_DB"), default=False),
    )
    if config:
        app.config.update(config)

    if is_production and not app.config.get("SQLALCHEMY_DATABASE_URI", "").startswith("postgresql"):
        raise RuntimeError("DATABASE_URL PostgreSQL wajib diatur sebelum menjalankan production.")
    if is_production and app.config["STORAGE_BACKEND"] != "vercel_blob":
        raise RuntimeError("Production wajib menggunakan STORAGE_BACKEND=vercel_blob.")
    if is_production and app.config["AUTO_INIT_DB"]:
        raise RuntimeError("AUTO_INIT_DB tidak boleh aktif di production; gunakan Flask-Migrate.")
    if app.config["STORAGE_BACKEND"] == "local":
        Path(app.config["UPLOAD_FOLDER"]).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    Migrate(app, db, compare_type=True)
    register_routes(app)
    register_cli(app)

    # Local convenience only. Production schema changes are controlled by Alembic.
    # Do not run create_all() during Vercel Function cold starts.
    if app.config["AUTO_INIT_DB"]:
        with app.app_context():
            db.create_all()
            bootstrap_data(app)

    return app


# --------------------------------------------------------------------------- helpers
def bootstrap_data(app):
    """Seed role catalog and optionally create a first admin when credentials exist."""
    for nama in ALL_ROLES:
        if not Role.query.filter_by(nama_role=nama).first():
            db.session.add(Role(nama_role=nama))
    db.session.commit()

    email = app.config.get("ADMIN_EMAIL")
    password = app.config.get("ADMIN_PASSWORD")
    if bool(email) != bool(password):
        raise RuntimeError("ADMIN_EMAIL dan ADMIN_PASSWORD harus diisi bersama-sama.")
    if email and not User.query.join(Role).filter(Role.nama_role == ROLE_ADMIN).first():
        make_user("Super Admin", email, password, ROLE_ADMIN)
        db.session.commit()


def make_user(nama, email, password, role):
    u = User(nama=nama, email=email.lower(),
             id_role=Role.query.filter_by(nama_role=role).one().id_role)
    u.set_password(password)
    db.session.add(u)
    return u


def current_user():
    uid = session.get("uid")
    return db.session.get(User, uid) if uid else None


def require(*roles):
    """Wajib login; jika roles diisi, role pengguna harus termasuk di dalamnya."""
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            u = current_user()
            if not u:
                raise ApiError("Silakan login terlebih dahulu.", 401)
            if roles and u.role.nama_role not in roles:
                raise ApiError("Anda tidak punya hak akses untuk aksi ini.", 403)
            return fn(u, *a, **kw)
        return wrapper
    return deco


def body():
    """Ambil data dari JSON atau form (multipart)."""
    return request.get_json(silent=True) or request.form.to_dict() or {}


def need(data, *fields):
    out = []
    for f in fields:
        v = (data.get(f) or "")
        v = v.strip() if isinstance(v, str) else v
        if v in ("", None):
            raise ApiError(f"Field '{f}' wajib diisi.")
        out.append(v)
    return out if len(out) > 1 else out[0]


def get_or_404(model, pk, label):
    obj = db.session.get(model, pk)
    if not obj:
        raise ApiError(f"{label} tidak ditemukan.", 404)
    return obj


def save_image(file_storage, *, prefix="uploads"):
    """Validate image bytes and persist them in configured private object storage."""
    if not file_storage or not file_storage.filename:
        raise ApiError("File gambar wajib diunggah.")

    filename = Path(file_storage.filename).name
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXT:
        raise ApiError("Format file harus PNG, JPG, atau WEBP.")

    content = file_storage.read(current_app.config["MAX_UPLOAD_BYTES"] + 1)
    if not content:
        raise ApiError("File gambar kosong.")
    if len(content) > current_app.config["MAX_UPLOAD_BYTES"]:
        raise ApiError("Ukuran file maksimal 4 MB.", 413)

    is_png = content.startswith(b"\x89PNG\r\n\x1a\n")
    is_jpeg = content.startswith(b"\xff\xd8\xff")
    is_webp = len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    valid = {"png": is_png, "jpg": is_jpeg, "jpeg": is_jpeg, "webp": is_webp}[ext]
    if not valid:
        raise ApiError("Isi file tidak sesuai dengan format gambar.")

    content_type = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                    "webp": "image/webp"}[ext]
    try:
        return get_storage().put(content, filename=filename, content_type=content_type, prefix=prefix)
    except Exception as exc:
        current_app.logger.exception("Private object storage upload failed")
        raise ApiError("Penyimpanan bukti sedang tidak tersedia. Coba lagi.", 503) from exc


def delete_image(storage_ref):
    """Best-effort cleanup after a successful database change or rollback."""
    if not storage_ref:
        return
    try:
        get_storage().delete(storage_ref)
    except Exception:
        current_app.logger.exception("Failed to delete orphaned private object: %s", storage_ref)


def can_read_file(user, storage_ref):
    """Authorize private file access using its owning domain record."""
    team_logo = TimEsports.query.filter_by(logo_url=storage_ref).first()
    if team_logo:
        return True  # team logos are public; match evidence remains restricted

    evidence = (HasilMatch.query.join(JadwalMatch).join(Turnamen)
                .filter(HasilMatch.foto_bukti_url == storage_ref).first())
    if not evidence or user is None:
        return False

    role = user.role.nama_role
    if role == ROLE_ADMIN:
        return True
    if role == ROLE_PANITIA:
        return evidence.jadwal.turnamen.id_panitia == user.id_user
    if role == ROLE_KAPTEN and user.tim:
        return user.tim.id_tim in (evidence.jadwal.id_tim_a, evidence.jadwal.id_tim_b)
    return False


def parse_dt(s):
    try:
        return datetime.fromisoformat(s)
    except (TypeError, ValueError):
        raise ApiError("Format tanggal/waktu tidak valid (gunakan YYYY-MM-DDTHH:MM).")


def owned_turnamen(user, id_turnamen):
    """Multi-tenant: Panitia hanya boleh mengelola turnamen miliknya sendiri."""
    t = get_or_404(Turnamen, id_turnamen, "Turnamen")
    if t.id_panitia != user.id_user:
        raise ApiError("Turnamen ini bukan milik Anda.", 403)
    return t


# --------------------------------------------------------------------------- routes
def register_routes(app):
    @app.errorhandler(ApiError)
    def on_api_error(e):
        return jsonify(error=e.message), e.status

    @app.errorhandler(404)
    def on_404(_):
        if request.path.startswith("/api/"):
            return jsonify(error="Endpoint tidak ditemukan."), 404
        if request.path.startswith(("/css/", "/js/")):
            return "Not found", 404
        return send_from_directory(app.config["PUBLIC_FOLDER"], "index.html")

    @app.errorhandler(413)
    def on_413(_):
        return jsonify(error="Ukuran file maksimal 4 MB."), 413

    @app.after_request
    def protect_private_responses(response):
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "private, no-store"
            response.headers["Vary"] = "Cookie"
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "base-uri 'self'; form-action 'self'; frame-ancestors 'none'; object-src 'none'; "
            "script-src 'self' https://cdn.jsdelivr.net; "
            "style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
            "font-src 'self' https://cdn.jsdelivr.net data:; "
            "img-src 'self' data:; connect-src 'self'",
        )
        return response

    @app.get("/")
    def index():
        return send_from_directory(app.config["PUBLIC_FOLDER"], "index.html")

    # Vercel serves public/** from its CDN. These routes provide the same paths locally.
    @app.get("/css/<path:name>")
    def css_asset(name):
        return send_from_directory(os.path.join(app.config["PUBLIC_FOLDER"], "css"), name)

    @app.get("/js/<path:name>")
    def js_asset(name):
        return send_from_directory(os.path.join(app.config["PUBLIC_FOLDER"], "js"), name)

    @app.get("/api/files/<token>")
    def private_file(token):
        actor = current_user()
        try:
            storage_ref = decode_file_token(token)
        except (ValueError, UnicodeError):
            raise ApiError("File tidak ditemukan.", 404)
        if not can_read_file(actor, storage_ref):
            raise ApiError("Anda tidak memiliki akses ke file ini.", 403)
        try:
            stored = get_storage().get(storage_ref)
        except FileNotFoundError:
            raise ApiError("File tidak ditemukan.", 404)
        except Exception as exc:
            current_app.logger.exception("Private object storage download failed")
            raise ApiError("File sedang tidak dapat diakses.", 503) from exc
        if stored.content_type not in {"image/png", "image/jpeg", "image/webp"}:
            raise ApiError("Tipe file tidak diizinkan.", 415)
        response = send_file(BytesIO(stored.body), mimetype=stored.content_type,
                             download_name=stored.filename, as_attachment=False, max_age=0)
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        return response

    # ---------------------------------------------------------------- auth
    @app.post("/api/auth/login")
    def login():
        d = body()
        email, pw = need(d, "email", "password")
        u = User.query.filter_by(email=email.lower()).first()
        if not u or not u.check_password(pw):
            raise ApiError("Email atau password salah.", 401)
        session.clear()
        session.permanent = True
        session["uid"] = u.id_user
        return jsonify(u.to_dict())

    @app.post("/api/auth/logout")
    def logout():
        session.clear()
        return jsonify(ok=True)

    @app.get("/api/auth/me")
    def me():
        u = current_user()
        return jsonify(u.to_dict() if u else None)

    @app.post("/api/auth/register")
    def register():
        """Admin boleh menentukan role (US-01). Tanpa login = daftar mandiri sebagai Kapten."""
        d = body()
        nama, email, pw = need(d, "nama", "email", "password")
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            raise ApiError("Format email tidak valid.")
        if len(pw) < 8:
            raise ApiError("Password minimal 8 karakter.")
        actor = current_user()
        role = ROLE_KAPTEN
        if actor and actor.role.nama_role == ROLE_ADMIN:
            role = d.get("role") or ROLE_KAPTEN
            if role not in ALL_ROLES:
                raise ApiError("Role tidak valid.")
        elif actor:
            raise ApiError("Anda sudah login.", 403)
        if User.query.filter_by(email=email.lower()).first():
            raise ApiError("Email sudah terdaftar.", 409)
        u = make_user(nama, email, pw, role)
        db.session.commit()
        return jsonify(u.to_dict()), 201

    # ---------------------------------------------------------------- users (US-01)
    @app.get("/api/users")
    @require(ROLE_ADMIN)
    def users(_u):
        return jsonify([x.to_dict() for x in User.query.order_by(User.id_user)])

    @app.patch("/api/users/<int:uid>/role")
    @require(ROLE_ADMIN)
    def set_role(actor, uid):
        target = get_or_404(User, uid, "Pengguna")
        role = need(body(), "role")
        if role not in ALL_ROLES:
            raise ApiError("Role tidak valid.")
        if target.id_user == actor.id_user and role != ROLE_ADMIN:
            raise ApiError("Anda tidak dapat menurunkan role akun sendiri.")
        target.id_role = Role.query.filter_by(nama_role=role).one().id_role
        db.session.commit()
        return jsonify(target.to_dict())

    # ---------------------------------------------------------------- turnamen (US-02)
    @app.get("/api/turnamen")
    def list_turnamen():
        u = current_user()
        q = Turnamen.query.order_by(Turnamen.tanggal_mulai.desc())
        if request.args.get("milik_saya") and u is not None and u.role.nama_role == ROLE_PANITIA:
            q = q.filter_by(id_panitia=u.id_user)
        return jsonify([t.to_dict(u) for t in q])

    @app.post("/api/turnamen")
    @require(ROLE_PANITIA)
    def create_turnamen(u):
        d = body()
        nama, tgl = need(d, "nama_turnamen", "tanggal_mulai")
        try:
            tgl = date.fromisoformat(tgl)
        except ValueError:
            raise ApiError("Format tanggal_mulai harus YYYY-MM-DD.")
        t = Turnamen(nama_turnamen=nama, tanggal_mulai=tgl, id_panitia=u.id_user)
        db.session.add(t)
        db.session.commit()
        return jsonify(t.to_dict(u)), 201

    @app.get("/api/turnamen/<int:tid>")
    def get_turnamen(tid):
        u = current_user()
        return jsonify(get_or_404(Turnamen, tid, "Turnamen").to_dict(u))

    @app.patch("/api/turnamen/<int:tid>")
    @require(ROLE_PANITIA)
    def update_turnamen(u, tid):
        t = owned_turnamen(u, tid)
        d = body()
        if d.get("status"):
            if d["status"] not in (TURNAMEN_AKTIF, TURNAMEN_SELESAI):
                raise ApiError("Status tidak valid.")
            t.status = d["status"]
        if d.get("nama_turnamen"):
            t.nama_turnamen = d["nama_turnamen"].strip()
        db.session.commit()
        return jsonify(t.to_dict(u))

    @app.get("/api/turnamen/<int:tid>/peserta")
    def peserta(tid):
        t = get_or_404(Turnamen, tid, "Turnamen")
        return jsonify([p.tim.to_dict() for p in t.pendaftar])

    # ---------------------------------------------------------------- tim (US-03)
    def daftarkan(tim, id_turnamen):
        t = get_or_404(Turnamen, id_turnamen, "Turnamen")
        if t.status != TURNAMEN_AKTIF:
            raise ApiError("Turnamen sudah tidak aktif.")
        if PendaftaranTurnamen.query.filter_by(id_turnamen=t.id_turnamen, id_tim=tim.id_tim).first():
            raise ApiError("Tim sudah terdaftar di turnamen ini.", 409)
        db.session.add(PendaftaranTurnamen(id_turnamen=t.id_turnamen, id_tim=tim.id_tim))

    @app.get("/api/tim")
    def list_tim():
        q = TimEsports.query.order_by(TimEsports.nama_tim)
        tid = request.args.get("turnamen_id", type=int)
        if tid:
            q = q.join(PendaftaranTurnamen).filter(PendaftaranTurnamen.id_turnamen == tid)
        return jsonify([t.to_dict() for t in q])

    @app.get("/api/tim/saya")
    @require(ROLE_KAPTEN)
    def tim_saya(u):
        return jsonify(u.tim.to_dict() if u.tim else None)

    @app.post("/api/tim")
    @require(ROLE_KAPTEN)
    def create_tim(u):
        if u.tim:
            raise ApiError("Anda sudah memiliki profil tim.", 409)
        d = body()
        nama = need(d, "nama_tim")
        if TimEsports.query.filter_by(nama_tim=nama).first():
            raise ApiError("Nama tim sudah dipakai.", 409)
        logo = save_image(request.files["logo"], prefix="team-logos") if request.files.get("logo") else None
        tim = TimEsports(nama_tim=nama, logo_url=logo, id_kapten=u.id_user)
        db.session.add(tim)
        try:
            db.session.flush()
            if d.get("id_turnamen"):
                daftarkan(tim, int(d["id_turnamen"]))
            db.session.commit()
        except (ApiError, ValueError, IntegrityError) as e:
            db.session.rollback()
            delete_image(logo)
            raise e if isinstance(e, ApiError) else ApiError("Data tim tidak valid.")
        return jsonify(tim.to_dict()), 201

    @app.put("/api/tim/saya")
    @require(ROLE_KAPTEN)
    def update_tim(u):
        if not u.tim:
            raise ApiError("Anda belum memiliki profil tim.", 404)
        d = body()
        if d.get("nama_tim"):
            nama = d["nama_tim"].strip()
            dup = TimEsports.query.filter(TimEsports.nama_tim == nama,
                                          TimEsports.id_tim != u.tim.id_tim).first()
            if dup:
                raise ApiError("Nama tim sudah dipakai.", 409)
            u.tim.nama_tim = nama
        old_logo = u.tim.logo_url
        new_logo = save_image(request.files["logo"], prefix="team-logos") if request.files.get("logo") else None
        if new_logo:
            u.tim.logo_url = new_logo
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            delete_image(new_logo)
            raise
        if new_logo and old_logo:
            delete_image(old_logo)
        return jsonify(u.tim.to_dict())

    @app.post("/api/turnamen/<int:tid>/daftar")
    @require(ROLE_KAPTEN)
    def daftar_turnamen(u, tid):
        if not u.tim:
            raise ApiError("Buat profil tim terlebih dahulu.")
        daftarkan(u.tim, tid)
        db.session.commit()
        return jsonify(ok=True), 201

    # ---------------------------------------------------------------- jadwal (US-04)
    @app.get("/api/jadwal")
    def list_jadwal():
        u = current_user()
        q = JadwalMatch.query.order_by(JadwalMatch.jadwal_main)
        tid = request.args.get("turnamen_id", type=int)
        if tid:
            q = q.filter_by(id_turnamen=tid)
        if request.args.get("milik_saya") and u is not None and u.tim:
            q = q.filter((JadwalMatch.id_tim_a == u.tim.id_tim) |
                         (JadwalMatch.id_tim_b == u.tim.id_tim))
        return jsonify([j.to_dict(u, public=u is None) for j in q])

    @app.post("/api/jadwal")
    @require(ROLE_PANITIA)
    def create_jadwal(u):
        d = body()
        tid, a, b, waktu = need(d, "id_turnamen", "id_tim_a", "id_tim_b", "jadwal_main")
        try:
            tid, a, b = int(tid), int(a), int(b)
        except (TypeError, ValueError):
            raise ApiError("ID turnamen/tim tidak valid.")
        t = owned_turnamen(u, tid)
        if t.status != TURNAMEN_AKTIF:
            raise ApiError("Turnamen sudah tidak aktif.")
        if a == b:
            raise ApiError("Tim A dan Tim B tidak boleh sama.")
        terdaftar = {p.id_tim for p in t.pendaftar}
        if a not in terdaftar or b not in terdaftar:
            raise ApiError("Kedua tim harus terdaftar di turnamen ini.")
        waktu = parse_dt(waktu)
        # cegah jadwal tumpang tindih: satu tim tidak boleh main di dua match pada waktu yang sama
        bentrok = JadwalMatch.query.filter(
            JadwalMatch.jadwal_main == waktu,
            (JadwalMatch.id_tim_a.in_([a, b])) | (JadwalMatch.id_tim_b.in_([a, b]))).first()
        if bentrok:
            raise ApiError("Salah satu tim sudah punya jadwal pada waktu yang sama.", 409)
        j = JadwalMatch(id_turnamen=tid, id_tim_a=a, id_tim_b=b, jadwal_main=waktu,
                        status_match=MATCH_MENUNGGU)
        db.session.add(j)
        db.session.commit()
        return jsonify(j.to_dict(u)), 201

    # ---------------------------------------------------------------- hasil (US-05, US-06)
    @app.post("/api/jadwal/<int:jid>/hasil")
    @require(ROLE_KAPTEN)
    def unggah_hasil(u, jid):
        j = get_or_404(JadwalMatch, jid, "Jadwal")
        if not u.tim or u.tim.id_tim not in (j.id_tim_a, j.id_tim_b):
            raise ApiError("Anda bukan kapten salah satu tim pada match ini.", 403)
        if j.turnamen.status != TURNAMEN_AKTIF:
            raise ApiError("Turnamen sudah tidak aktif.")
        if j.hasil and j.hasil.status_validasi != VALID_TOLAK:
            raise ApiError("Hasil match ini sudah diunggah / divalidasi.", 409)
        url = save_image(request.files.get("foto"), prefix="match-evidence")
        old_url = j.hasil.foto_bukti_url if j.hasil else None
        if j.hasil:  # unggah ulang setelah ditolak: ganti bukti lama
            h = j.hasil
            h.foto_bukti_url, h.id_pemenang = url, u.tim.id_tim
            h.status_validasi, h.catatan_validasi = VALID_MENUNGGU, None
            h.waktu_unggah = utcnow_naive()
        else:
            h = HasilMatch(id_jadwal=j.id_jadwal, id_pemenang=u.tim.id_tim, foto_bukti_url=url)
            db.session.add(h)
        j.status_match = MATCH_DIPROSES
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            delete_image(url)
            raise
        if old_url:
            delete_image(old_url)
        return jsonify(h.to_dict()), 201

    @app.get("/api/hasil")
    @require(ROLE_PANITIA, ROLE_ADMIN)
    def list_hasil(u):
        q = (HasilMatch.query.join(JadwalMatch).join(Turnamen)
             .order_by(HasilMatch.waktu_unggah.desc()))
        if u.role.nama_role == ROLE_PANITIA:  # hanya turnamen miliknya
            q = q.filter(Turnamen.id_panitia == u.id_user)
        if request.args.get("status"):
            q = q.filter(HasilMatch.status_validasi == request.args["status"])
        return jsonify([{**h.to_dict(), "jadwal": h.jadwal.to_dict()} for h in q])

    @app.patch("/api/hasil/<int:hid>/validasi")
    @require(ROLE_PANITIA)
    def validasi(u, hid):
        h = get_or_404(HasilMatch, hid, "Hasil match")
        owned_turnamen(u, h.jadwal.id_turnamen)
        if h.status_validasi != VALID_MENUNGGU:
            raise ApiError("Hasil ini sudah divalidasi.", 409)
        d = body()
        keputusan = need(d, "keputusan")
        if keputusan == "setuju":
            h.status_validasi, h.jadwal.status_match = VALID_SETUJU, MATCH_SELESAI
        elif keputusan == "tolak":
            h.status_validasi = VALID_TOLAK
            h.catatan_validasi = (d.get("catatan") or "").strip()[:255] or None
            h.jadwal.status_match = MATCH_MENUNGGU  # kapten boleh unggah ulang
        else:
            raise ApiError("keputusan harus 'setuju' atau 'tolak'.")
        db.session.commit()
        return jsonify(h.to_dict())


# --------------------------------------------------------------------------- CLI
def register_cli(app):
    @app.cli.command("init-db")
    def init_db():
        """Create the schema for local development; production should use migrations."""
        db.create_all()
        bootstrap_data(app)
        print("Database schema and role catalog are ready.")

    @app.cli.command("bootstrap")
    def bootstrap():
        """Seed roles and optionally provision the first admin from environment variables."""
        bootstrap_data(app)
        if app.config.get("ADMIN_EMAIL") and app.config.get("ADMIN_PASSWORD"):
            print(f"Initial admin is ready: {app.config['ADMIN_EMAIL']}")
        else:
            print("Role catalog is ready; no admin created (set ADMIN_EMAIL and ADMIN_PASSWORD first).")

    @app.cli.command("seed-demo")
    def seed_demo():
        """Isi data fiktif untuk demo: 1 panitia, 4 kapten/tim, 1 turnamen, 2 jadwal."""
        if User.query.filter_by(email="panitia@demo.id").first():
            print("Data demo sudah ada.")
            return
        make_user("Panitia Demo", "panitia@demo.id", "demo12345", ROLE_PANITIA)
        db.session.flush()
        panitia = User.query.filter_by(email="panitia@demo.id").one()
        t = Turnamen(nama_turnamen="Tazkia Cup 2026 - Mobile Legends",
                     tanggal_mulai=date(2026, 11, 20), id_panitia=panitia.id_user)
        db.session.add(t)
        tims = []
        for i, nama in enumerate(["Garuda Esports", "Bogor Raiders", "Pixel Wolves", "Nusa Gaming"], 1):
            k = make_user(f"Kapten {i}", f"kapten{i}@demo.id", "demo12345", ROLE_KAPTEN)
            db.session.flush()
            tim = TimEsports(nama_tim=nama, id_kapten=k.id_user)
            db.session.add(tim)
            db.session.flush()
            db.session.add(PendaftaranTurnamen(id_turnamen=t.id_turnamen, id_tim=tim.id_tim))
            tims.append(tim)
        db.session.flush()
        db.session.add(JadwalMatch(id_turnamen=t.id_turnamen, id_tim_a=tims[0].id_tim,
                                   id_tim_b=tims[1].id_tim, jadwal_main=datetime(2026, 11, 20, 13, 0)))
        db.session.add(JadwalMatch(id_turnamen=t.id_turnamen, id_tim_a=tims[2].id_tim,
                                   id_tim_b=tims[3].id_tim, jadwal_main=datetime(2026, 11, 20, 15, 0)))
        db.session.commit()
        print("Data demo dibuat. Login: panitia@demo.id / kapten1@demo.id ... kapten4@demo.id "
              "(password: demo12345)")


app = create_app()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", port=int(os.environ.get("PORT", 5000)))
