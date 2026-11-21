"""Materi 4 Minggu 7: Tambah ruangan, dosen, kelas, jadwal, krs_detail.kelas_id

Revision ID: 002_modul_jadwal_ruangan
Revises: 001_baseline_krs
Create Date: 2026-11-20 17:36:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002_modul_jadwal_ruangan"
down_revision: Union[str, Sequence[str], None] = "001_baseline_krs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ruangan",
        sa.Column("kode", sa.String(length=20), primary_key=True),
        sa.Column("nama", sa.String(length=100), nullable=False),
        sa.Column("kapasitas", sa.Integer(), nullable=False),
    )

    op.create_table(
        "dosen",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("nidn", sa.String(length=20), nullable=False, unique=True),
        sa.Column("nama", sa.String(length=100), nullable=False),
    )

    op.create_table(
        "kelas",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "kode_mk",
            sa.String(length=20),
            sa.ForeignKey("matakuliah.kode_mk"),
            nullable=False,
        ),
        sa.Column("nama_kelas", sa.String(length=10), nullable=False),
        sa.Column("kuota", sa.Integer(), nullable=False),
        sa.Column("semester", sa.String(length=10), nullable=False),
    )

    op.create_table(
        "jadwal",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "kelas_id",
            sa.Integer(),
            sa.ForeignKey("kelas.id"),
            nullable=False,
        ),
        sa.Column("hari", sa.Integer(), nullable=False),
        sa.Column("jam_mulai", sa.Time(), nullable=False),
        sa.Column("jam_selesai", sa.Time(), nullable=False),
        sa.Column(
            "ruangan_kode",
            sa.String(length=20),
            sa.ForeignKey("ruangan.kode"),
            nullable=False,
        ),
        sa.Column(
            "dosen_id",
            sa.Integer(),
            sa.ForeignKey("dosen.id"),
            nullable=False,
        ),
        sa.CheckConstraint("jam_mulai < jam_selesai", name="ck_jadwal_jam_valid"),
        sa.CheckConstraint("hari BETWEEN 1 AND 6", name="ck_jadwal_hari_valid"),
    )
    op.create_index("ix_jadwal_ruangan", "jadwal", ["hari", "ruangan_kode"])
    op.create_index("ix_jadwal_dosen", "jadwal", ["hari", "dosen_id"])

    # Pindahkan hari & jam keluar dari matakuliah
    with op.batch_alter_table("matakuliah") as batch_op:
        batch_op.drop_column("hari")
        batch_op.drop_column("jam_mulai")
        batch_op.drop_column("jam_selesai")

    # Tambahkan kolom kelas_id di krs_detail untuk capacity check (integrasi penuh Minggu 8)
    with op.batch_alter_table("krs_detail") as batch_op:
        batch_op.add_column(sa.Column("kelas_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_krs_detail_kelas_id",
            "kelas",
            ["kelas_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("krs_detail") as batch_op:
        batch_op.drop_constraint("fk_krs_detail_kelas_id", type_="foreignkey")
        batch_op.drop_column("kelas_id")

    with op.batch_alter_table("matakuliah") as batch_op:
        batch_op.add_column(sa.Column("hari", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("jam_mulai", sa.Time(), nullable=True))
        batch_op.add_column(sa.Column("jam_selesai", sa.Time(), nullable=True))

    op.drop_index("ix_jadwal_dosen", table_name="jadwal")
    op.drop_index("ix_jadwal_ruangan", table_name="jadwal")
    op.drop_table("jadwal")
    op.drop_table("kelas")
    op.drop_table("dosen")
    op.drop_table("ruangan")
