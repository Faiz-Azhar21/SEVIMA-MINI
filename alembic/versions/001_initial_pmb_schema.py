"""Initial PMB schema (program_studi, jalur_masuk, calon_mahasiswa).

Revision ID: 001_initial_pmb
Revises:
Create Date: 2026-11-20 14:00:00
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001_initial_pmb"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "program_studi",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("kode", sa.String(length=10), nullable=False),
        sa.Column("nama", sa.String(length=120), nullable=False),
        sa.Column("fakultas", sa.String(length=120), nullable=False),
        sa.UniqueConstraint("kode", name="uq_program_studi_kode"),
    )
    op.create_index("ix_program_studi_kode", "program_studi", ["kode"], unique=True)

    op.create_table(
        "jalur_masuk",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("kode", sa.String(length=20), nullable=False),
        sa.Column("nama", sa.String(length=100), nullable=False),
        sa.Column("deskripsi", sa.Text(), nullable=True),
        sa.UniqueConstraint("kode", name="uq_jalur_masuk_kode"),
        sa.CheckConstraint(
            "kode IN ('SNBP', 'SNBT', 'Mandiri')",
            name="ck_jalur_masuk_kode",
        ),
    )
    op.create_index("ix_jalur_masuk_kode", "jalur_masuk", ["kode"], unique=True)

    op.create_table(
        "calon_mahasiswa",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("nama_lengkap", sa.String(length=150), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("tanggal_lahir", sa.Date(), nullable=False),
        sa.Column("alamat", sa.Text(), nullable=False),
        sa.Column("program_studi_id", sa.Integer(), nullable=False),
        sa.Column("jalur_masuk", sa.String(length=20), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "approved", "rejected", name="status_pmb_enum"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["program_studi_id"],
            ["program_studi.id"],
            name="fk_calon_program_studi",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["jalur_masuk"],
            ["jalur_masuk.kode"],
            name="fk_calon_jalur_masuk",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("email", name="uq_calon_mahasiswa_email"),
        sa.CheckConstraint(
            "email LIKE '%_@__%.__%'",
            name="ck_calon_email_format",
        ),
        sa.CheckConstraint(
            "(phone LIKE '08%' OR phone LIKE '+628%' OR phone LIKE '628%') "
            "AND length(phone) >= 10 AND length(phone) <= 15",
            name="ck_calon_phone_indonesia",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_calon_status_enum",
        ),
        sa.CheckConstraint(
            "jalur_masuk IN ('SNBP', 'SNBT', 'Mandiri')",
            name="ck_calon_jalur_masuk_enum",
        ),
    )
    op.create_index("ix_calon_mahasiswa_email", "calon_mahasiswa", ["email"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_calon_mahasiswa_email", table_name="calon_mahasiswa")
    op.drop_table("calon_mahasiswa")

    op.drop_index("ix_jalur_masuk_kode", table_name="jalur_masuk")
    op.drop_table("jalur_masuk")

    op.drop_index("ix_program_studi_kode", table_name="program_studi")
    op.drop_table("program_studi")
