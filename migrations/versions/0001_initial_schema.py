"""Initial Tanding.in schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-11-08
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "roles",
        sa.Column("id_role", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("nama_role", sa.String(length=30), nullable=False, unique=True),
    )

    op.create_table(
        "users",
        sa.Column("id_user", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("nama", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=150), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("id_role", sa.Integer(), sa.ForeignKey("roles.id_role"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=False)

    op.create_table(
        "tim_esports",
        sa.Column("id_tim", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("nama_tim", sa.String(length=100), nullable=False, unique=True),
        sa.Column("logo_url", sa.String(length=255), nullable=True),
        sa.Column("id_kapten", sa.Integer(), sa.ForeignKey("users.id_user"), nullable=False, unique=True),
    )

    op.create_table(
        "turnamen",
        sa.Column("id_turnamen", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("nama_turnamen", sa.String(length=150), nullable=False),
        sa.Column("tanggal_mulai", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("id_panitia", sa.Integer(), sa.ForeignKey("users.id_user"), nullable=False),
    )

    op.create_table(
        "pendaftaran_turnamen",
        sa.Column("id_pendaftaran", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("id_turnamen", sa.Integer(), sa.ForeignKey("turnamen.id_turnamen"), nullable=False),
        sa.Column("id_tim", sa.Integer(), sa.ForeignKey("tim_esports.id_tim"), nullable=False),
        sa.Column("waktu_daftar", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("id_turnamen", "id_tim", name="uq_turnamen_tim"),
    )

    op.create_table(
        "jadwal_match",
        sa.Column("id_jadwal", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("id_turnamen", sa.Integer(), sa.ForeignKey("turnamen.id_turnamen"), nullable=False),
        sa.Column("id_tim_a", sa.Integer(), sa.ForeignKey("tim_esports.id_tim"), nullable=False),
        sa.Column("id_tim_b", sa.Integer(), sa.ForeignKey("tim_esports.id_tim"), nullable=False),
        sa.Column("jadwal_main", sa.DateTime(), nullable=False),
        sa.Column("status_match", sa.String(length=20), nullable=False),
    )

    op.create_table(
        "hasil_match",
        sa.Column("id_hasil", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("id_jadwal", sa.Integer(), sa.ForeignKey("jadwal_match.id_jadwal"), nullable=False, unique=True),
        sa.Column("id_pemenang", sa.Integer(), sa.ForeignKey("tim_esports.id_tim"), nullable=False),
        sa.Column("foto_bukti_url", sa.String(length=255), nullable=False),
        sa.Column("status_validasi", sa.String(length=20), nullable=False),
        sa.Column("catatan_validasi", sa.String(length=255), nullable=True),
        sa.Column("waktu_unggah", sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table("hasil_match")
    op.drop_table("jadwal_match")
    op.drop_table("pendaftaran_turnamen")
    op.drop_table("turnamen")
    op.drop_table("tim_esports")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    op.drop_table("roles")
