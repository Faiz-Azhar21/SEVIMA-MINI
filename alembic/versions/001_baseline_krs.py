"""Baseline Materi 3: Modul KRS (matakuliah dengan hari/jam lama, krs, krs_detail)

Revision ID: 001_baseline_krs
Revises:
Create Date: 2026-11-20 17:35:00
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001_baseline_krs"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "matakuliah",
        sa.Column("kode_mk", sa.String(length=20), primary_key=True),
        sa.Column("nama", sa.String(length=100), nullable=False),
        sa.Column("sks", sa.Integer(), nullable=False),
        # Kolom legacy dari Minggu 5-6 (sebelum jadwal dipisah ke tabel jadwal)
        sa.Column("hari", sa.Integer(), nullable=True),
        sa.Column("jam_mulai", sa.Time(), nullable=True),
        sa.Column("jam_selesai", sa.Time(), nullable=True),
    )
    op.create_table(
        "krs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("nim", sa.String(length=20), nullable=False),
        sa.Column("semester", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
    )
    op.create_index("ix_krs_nim", "krs", ["nim"])

    op.create_table(
        "krs_detail",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "krs_id",
            sa.Integer(),
            sa.ForeignKey("krs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "kode_mk",
            sa.String(length=20),
            sa.ForeignKey("matakuliah.kode_mk"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("krs_detail")
    op.drop_index("ix_krs_nim", table_name="krs")
    op.drop_table("krs")
    op.drop_table("matakuliah")
