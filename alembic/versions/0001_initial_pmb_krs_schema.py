"""Initial schema PMB minimal + Modul KRS (matakuliah, prerequisite, skala_nilai, krs, krs_detail).

Revision ID: 0001_initial_pmb_krs
Revises:
Create Date: 2026-11-20
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_initial_pmb_krs"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Tabel calon_mahasiswa (minimal dari Modul PMB Minggu 3-4)
    op.create_table(
        "calon_mahasiswa",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("nama", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=120), nullable=False),
        sa.Column("prodi", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="PENDING"),
        sa.Column("nim", sa.String(length=20), nullable=True),
        sa.UniqueConstraint("email", name="uq_calon_mahasiswa_email"),
        sa.UniqueConstraint("nim", name="uq_calon_mahasiswa_nim"),
    )

    # 2. Tabel bantu skala_nilai (pemetaan huruf -> bobot numerik)
    op.create_table(
        "skala_nilai",
        sa.Column("huruf", sa.String(length=2), primary_key=True),
        sa.Column("bobot", sa.Numeric(precision=3, scale=2), nullable=False),
    )

    # 3. Tabel matakuliah (beserta CHECK constraint SKS 1-4, hari 1-6, jam_mulai < jam_selesai)
    op.create_table(
        "matakuliah",
        sa.Column("kode_mk", sa.String(length=10), primary_key=True),
        sa.Column("nama", sa.String(length=100), nullable=False),
        sa.Column("sks", sa.Integer(), nullable=False),
        sa.Column("hari", sa.Integer(), nullable=False),
        sa.Column("jam_mulai", sa.Time(), nullable=False),
        sa.Column("jam_selesai", sa.Time(), nullable=False),
        sa.CheckConstraint("sks BETWEEN 1 AND 4", name="ck_matakuliah_sks_range"),
        sa.CheckConstraint("hari BETWEEN 1 AND 6", name="ck_matakuliah_hari_range"),
        sa.CheckConstraint("jam_mulai < jam_selesai", name="ck_matakuliah_jam_valid"),
    )

    # 4. Tabel prerequisite (self-referencing many-to-many pada matakuliah)
    op.create_table(
        "prerequisite",
        sa.Column("kode_mk", sa.String(length=10), nullable=False),
        sa.Column("kode_prasyarat", sa.String(length=10), nullable=False),
        sa.ForeignKeyConstraint(["kode_mk"], ["matakuliah.kode_mk"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["kode_prasyarat"], ["matakuliah.kode_mk"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("kode_mk", "kode_prasyarat", name="pk_prerequisite"),
        sa.CheckConstraint("kode_mk <> kode_prasyarat", name="ck_prerequisite_not_self"),
    )

    # 5. Tabel krs (header satu kartu KRS per mahasiswa per semester)
    # UNIQUE (nim, semester) sekaligus menjadi composite index optimal untuk
    # query `WHERE k.nim = :nim AND k.semester < :semester` (equality di depan, range di belakang).
    op.create_table(
        "krs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("nim", sa.String(length=20), nullable=False),
        sa.Column("semester", sa.String(length=5), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
        sa.Column("dosen_pa_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["nim"], ["calon_mahasiswa.nim"], ondelete="RESTRICT"),
        sa.UniqueConstraint("nim", "semester", name="uq_krs_nim_semester"),
    )

    # 6. Tabel krs_detail (baris MK dalam satu KRS + nilai nullable)
    # UNIQUE (krs_id, kode_mk) menjadi lapis pertahanan DB anti double enrollment
    # sekaligus index utama pencarian prasyarat.
    op.create_table(
        "krs_detail",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("krs_id", sa.Integer(), nullable=False),
        sa.Column("kode_mk", sa.String(length=10), nullable=False),
        sa.Column("nilai", sa.String(length=2), nullable=True),
        sa.ForeignKeyConstraint(["krs_id"], ["krs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["kode_mk"], ["matakuliah.kode_mk"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["nilai"], ["skala_nilai.huruf"], ondelete="RESTRICT"),
        sa.UniqueConstraint("krs_id", "kode_mk", name="uq_krs_detail_krs_mk"),
    )


def downgrade() -> None:
    op.drop_table("krs_detail")
    op.drop_table("krs")
    op.drop_table("prerequisite")
    op.drop_table("matakuliah")
    op.drop_table("skala_nilai")
    op.drop_table("calon_mahasiswa")
