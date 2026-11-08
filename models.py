"""Model basis data Tanding.in (Bab 7.2 proposal).

Tabel sesuai proposal: roles, users, tim_esports, turnamen, jadwal_match, hasil_match.
Tambahan: pendaftaran_turnamen (relasi tim <-> turnamen untuk US-03), lihat README.
"""
from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

from storage import file_url

db = SQLAlchemy()


def utcnow_naive():
    """Return UTC as a naive datetime for legacy TIMESTAMP WITHOUT TIME ZONE columns.

    Existing schema and SQLite data store these values as UTC-naive timestamps.
    Keep that representation stable while avoiding deprecated datetime.utcnow().
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)

ROLE_ADMIN = "super_admin"
ROLE_PANITIA = "panitia"
ROLE_KAPTEN = "kapten"
ALL_ROLES = [ROLE_ADMIN, ROLE_PANITIA, ROLE_KAPTEN]

# Status turnamen
TURNAMEN_AKTIF = "aktif"
TURNAMEN_SELESAI = "selesai"

# Status match (Tabel 11)
MATCH_MENUNGGU = "Menunggu"
MATCH_DIPROSES = "Diproses"
MATCH_SELESAI = "Selesai"

# Status validasi hasil
VALID_MENUNGGU = "Menunggu"
VALID_SETUJU = "Disetujui"
VALID_TOLAK = "Ditolak"


def iso(dt):
    return dt.isoformat(timespec="minutes") if dt else None


class Role(db.Model):
    __tablename__ = "roles"
    id_role = db.Column(db.Integer, primary_key=True)
    nama_role = db.Column(db.String(30), unique=True, nullable=False)


class User(db.Model):
    __tablename__ = "users"
    id_user = db.Column(db.Integer, primary_key=True)
    nama = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    id_role = db.Column(db.Integer, db.ForeignKey("roles.id_role"), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow_naive)

    role = db.relationship("Role")
    tim = db.relationship("TimEsports", back_populates="kapten", uselist=False)
    turnamen = db.relationship("Turnamen", back_populates="panitia")

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)

    def to_dict(self):
        return {
            "id_user": self.id_user,
            "nama": self.nama,
            "email": self.email,
            "role": self.role.nama_role,
            "id_tim": self.tim.id_tim if self.tim else None,
        }


class TimEsports(db.Model):
    __tablename__ = "tim_esports"
    id_tim = db.Column(db.Integer, primary_key=True)
    nama_tim = db.Column(db.String(100), unique=True, nullable=False)
    logo_url = db.Column(db.String(255))
    # users - tim_esports 1:1 (unique)
    id_kapten = db.Column(db.Integer, db.ForeignKey("users.id_user"), unique=True, nullable=False)

    kapten = db.relationship("User", back_populates="tim")

    def to_dict(self):
        return {
            "id_tim": self.id_tim,
            "nama_tim": self.nama_tim,
            "logo_url": file_url(self.logo_url),
            "kapten": self.kapten.nama,
        }


class Turnamen(db.Model):
    __tablename__ = "turnamen"
    id_turnamen = db.Column(db.Integer, primary_key=True)
    nama_turnamen = db.Column(db.String(150), nullable=False)
    tanggal_mulai = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), nullable=False, default=TURNAMEN_AKTIF)
    id_panitia = db.Column(db.Integer, db.ForeignKey("users.id_user"), nullable=False)

    panitia = db.relationship("User", back_populates="turnamen")
    pendaftar = db.relationship("PendaftaranTurnamen", cascade="all, delete-orphan")
    jadwal = db.relationship("JadwalMatch", back_populates="turnamen")

    def to_dict(self, viewer=None):
        d = {
            "id_turnamen": self.id_turnamen,
            "nama_turnamen": self.nama_turnamen,
            "tanggal_mulai": self.tanggal_mulai.isoformat(),
            "status": self.status,
            "panitia": self.panitia.nama,
            "id_panitia": self.id_panitia,
            "jumlah_tim": len(self.pendaftar),
        }
        if viewer is not None and viewer.tim:
            d["saya_terdaftar"] = any(p.id_tim == viewer.tim.id_tim for p in self.pendaftar)
        return d


class PendaftaranTurnamen(db.Model):
    __tablename__ = "pendaftaran_turnamen"
    id_pendaftaran = db.Column(db.Integer, primary_key=True)
    id_turnamen = db.Column(db.Integer, db.ForeignKey("turnamen.id_turnamen"), nullable=False)
    id_tim = db.Column(db.Integer, db.ForeignKey("tim_esports.id_tim"), nullable=False)
    waktu_daftar = db.Column(db.DateTime, default=utcnow_naive)
    __table_args__ = (db.UniqueConstraint("id_turnamen", "id_tim", name="uq_turnamen_tim"),)

    tim = db.relationship("TimEsports")


class JadwalMatch(db.Model):
    __tablename__ = "jadwal_match"
    id_jadwal = db.Column(db.Integer, primary_key=True)
    id_turnamen = db.Column(db.Integer, db.ForeignKey("turnamen.id_turnamen"), nullable=False)
    id_tim_a = db.Column(db.Integer, db.ForeignKey("tim_esports.id_tim"), nullable=False)
    id_tim_b = db.Column(db.Integer, db.ForeignKey("tim_esports.id_tim"), nullable=False)
    jadwal_main = db.Column(db.DateTime, nullable=False)
    status_match = db.Column(db.String(20), nullable=False, default=MATCH_MENUNGGU)

    turnamen = db.relationship("Turnamen", back_populates="jadwal")
    tim_a = db.relationship("TimEsports", foreign_keys=[id_tim_a])
    tim_b = db.relationship("TimEsports", foreign_keys=[id_tim_b])
    hasil = db.relationship("HasilMatch", back_populates="jadwal", uselist=False,
                            cascade="all, delete-orphan")

    def to_dict(self, viewer=None):
        d = {
            "id_jadwal": self.id_jadwal,
            "turnamen": {"id_turnamen": self.turnamen.id_turnamen,
                         "nama_turnamen": self.turnamen.nama_turnamen},
            "tim_a": self.tim_a.to_dict(),
            "tim_b": self.tim_b.to_dict(),
            "jadwal_main": iso(self.jadwal_main),
            "status_match": self.status_match,
            "hasil": self.hasil.to_dict() if self.hasil else None,
        }
        if viewer is not None and viewer.tim:
            mine = viewer.tim.id_tim in (self.id_tim_a, self.id_tim_b)
            boleh_ulang = self.hasil is None or self.hasil.status_validasi == VALID_TOLAK
            d["milik_saya"] = mine
            d["bisa_unggah"] = (mine and boleh_ulang
                                and self.turnamen.status == TURNAMEN_AKTIF)
        return d


class HasilMatch(db.Model):
    __tablename__ = "hasil_match"
    id_hasil = db.Column(db.Integer, primary_key=True)
    # jadwal_match - hasil_match 1:1 (unique)
    id_jadwal = db.Column(db.Integer, db.ForeignKey("jadwal_match.id_jadwal"),
                          unique=True, nullable=False)
    id_pemenang = db.Column(db.Integer, db.ForeignKey("tim_esports.id_tim"), nullable=False)
    foto_bukti_url = db.Column(db.String(255), nullable=False)
    status_validasi = db.Column(db.String(20), nullable=False, default=VALID_MENUNGGU)
    catatan_validasi = db.Column(db.String(255))
    waktu_unggah = db.Column(db.DateTime, default=utcnow_naive)

    jadwal = db.relationship("JadwalMatch", back_populates="hasil")
    pemenang = db.relationship("TimEsports")

    def to_dict(self):
        return {
            "id_hasil": self.id_hasil,
            "id_jadwal": self.id_jadwal,
            "id_pemenang": self.id_pemenang,
            "nama_pemenang": self.pemenang.nama_tim,
            "foto_bukti_url": file_url(self.foto_bukti_url),
            "status_validasi": self.status_validasi,
            "catatan_validasi": self.catatan_validasi,
            "waktu_unggah": iso(self.waktu_unggah),
        }
