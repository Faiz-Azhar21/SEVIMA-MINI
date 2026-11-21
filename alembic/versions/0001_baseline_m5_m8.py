"""Baseline skema Minggu 5-8 (akademik, jadwal, krs, skala_nilai awal).

Revision ID: 0001_baseline_m5_m8
Revises:
Create Date: 2026-11-22
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_baseline_m5_m8"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mahasiswa",
        sa.Column("nim", sa.String(length=20), primary_key=True),
        sa.Column("nama", sa.String(length=120), nullable=False),
        sa.Column("prodi", sa.String(length=100), nullable=False),
        sa.Column("angkatan", sa.Integer(), nullable=False),
    )

    op.create_table(
        "dosen",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("nidn", sa.String(length=20), nullable=False, unique=True),
        sa.Column("nama", sa.String(length=120), nullable=False),
    )

    op.create_table(
        "matakuliah",
        sa.Column("kode_mk", sa.String(length=20), primary_key=True),
        sa.Column("nama_mk", sa.String(length=150), nullable=False),
        sa.Column("sks", sa.Integer(), nullable=False),
    )

    op.create_table(
        "skala_nilai",
        sa.Column("huruf", sa.String(length=2), primary_key=True),
        sa.Column("bobot", sa.Float(), nullable=False),  # sebelum M9 ditingkatkan ke Numeric(3,2)
    )

    op.create_table(
        "kelas",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("kode_mk", sa.String(length=20), sa.ForeignKey("matakuliah.kode_mk"), nullable=False),
        sa.Column("nama_kelas", sa.String(length=50), nullable=False),
        sa.Column("semester", sa.String(length=10), nullable=False),
    )

    op.create_table(
        "jadwal",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("kelas_id", sa.Integer(), sa.ForeignKey("kelas.id"), nullable=False),
        sa.Column("dosen_id", sa.Integer(), sa.ForeignKey("dosen.id"), nullable=False),
        sa.Column("ruangan", sa.String(length=50), nullable=False, server_default="R-101"),
        sa.Column("hari", sa.String(length=20), nullable=False, server_default="Senin"),
        sa.Column("jam_mulai", sa.String(length=5), nullable=False, server_default="08:00"),
        sa.Column("jam_selesai", sa.String(length=5), nullable=False, server_default="10:00"),
    )
    op.create_index("ix_jadwal_kelas_id", "jadwal", ["kelas_id"])
    op.create_index("ix_jadwal_dosen_id", "jadwal", ["dosen_id"])

    op.create_table(
        "krs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("nim", sa.String(length=20), sa.ForeignKey("mahasiswa.nim"), nullable=False),
        sa.Column("semester", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="APPROVED"),
        sa.UniqueConstraint("nim", "semester", name="uq_krs_nim_semester"),
    )
    op.create_index("ix_krs_nim", "krs", ["nim"])

    op.create_table(
        "krs_detail",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("krs_id", sa.Integer(), sa.ForeignKey("krs.id"), nullable=False),
        sa.Column("kode_mk", sa.String(length=20), sa.ForeignKey("matakuliah.kode_mk"), nullable=False),
        sa.Column("kelas_id", sa.Integer(), sa.ForeignKey("kelas.id"), nullable=False),
        # Sejak Minggu 5: kolom nilai masih nullable tanpa FK ke skala_nilai
        sa.Column("nilai", sa.String(length=2), nullable=True),
        sa.UniqueConstraint("krs_id", "kelas_id", name="uq_krs_detail_krs_kelas"),
    )
    op.create_index("ix_krs_detail_krs_id", "krs_detail", ["krs_id"])
    op.create_index("ix_krs_detail_kelas_id", "krs_detail", ["kelas_id"])


def downgrade() -> None:
    op.drop_table("krs_detail")
    op.drop_table("krs")
    op.drop_table("jadwal")
    op.drop_table("kelas")
    op.drop_table("skala_nilai")
    op.drop_table("matakuliah")
    op.drop_table("dosen")
    op.drop_table("mahasiswa")
