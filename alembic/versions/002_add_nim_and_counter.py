"""Add unique nim column to calon_mahasiswa and create nim_counter table.

Revision ID: 002_nim_and_counter
Revises: 001_initial_pmb
Create Date: 2026-11-20 14:05:00
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_nim_and_counter"
down_revision: Union[str, Sequence[str], None] = "001_initial_pmb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("calon_mahasiswa", schema=None) as batch_op:
        batch_op.add_column(sa.Column("nim", sa.String(length=12), nullable=True))
        batch_op.create_unique_constraint("uq_calon_mahasiswa_nim", ["nim"])
        batch_op.create_index("ix_calon_mahasiswa_nim", ["nim"], unique=True)

    op.create_table(
        "nim_counter",
        sa.Column("tahun", sa.Integer(), primary_key=True),
        sa.Column("kode_prodi", sa.String(length=3), primary_key=True),
        sa.Column("last_number", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint(
            "last_number >= 0 AND last_number <= 9999",
            name="ck_nim_counter_range",
        ),
    )


def downgrade() -> None:
    op.drop_table("nim_counter")

    with op.batch_alter_table("calon_mahasiswa", schema=None) as batch_op:
        batch_op.drop_index("ix_calon_mahasiswa_nim")
        batch_op.drop_constraint("uq_calon_mahasiswa_nim", type_="unique")
        batch_op.drop_column("nim")
