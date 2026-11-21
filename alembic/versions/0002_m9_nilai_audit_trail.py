"""Minggu 9: FK krs_detail.nilai, skala_nilai.lulus & Numeric(3,2), grade_history, view v_riwayat_nilai.

Revision ID: 0002_m9_nilai_audit_trail
Revises: 0001_baseline_m5_m8
Create Date: 2026-11-22
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from app.models.nilai import VIEW_RIWAYAT_NILAI_SQL

revision = "0002_m9_nilai_audit_trail"
down_revision = "0001_baseline_m5_m8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Tingkatkan skala_nilai: bobot -> Numeric(3,2) dan tambah kolom lulus (Boolean)
    with op.batch_alter_table("skala_nilai") as batch_op:
        batch_op.alter_column(
            "bobot",
            existing_type=sa.Float(),
            type_=sa.Numeric(3, 2),
            existing_nullable=False,
        )
        batch_op.add_column(
            sa.Column("lulus", sa.Boolean(), nullable=False, server_default=sa.false())
        )

    # Set asumsi sementara: A, B, C lulus (minimal C = 2.00; lihat ADR-005)
    op.execute("UPDATE skala_nilai SET lulus = 1 WHERE huruf IN ('A', 'B', 'C')")

    # 2. Tambah Foreign Key krs_detail.nilai -> skala_nilai.huruf
    with op.batch_alter_table("krs_detail") as batch_op:
        batch_op.create_foreign_key(
            "fk_krs_detail_nilai_skala_nilai",
            "skala_nilai",
            ["nilai"],
            ["huruf"],
        )

    # 3. Buat tabel audit trail append-only: grade_history
    op.create_table(
        "grade_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("grade_id", sa.Integer(), sa.ForeignKey("krs_detail.id"), nullable=False),
        sa.Column("old_value", sa.String(length=2), nullable=True),
        sa.Column("new_value", sa.String(length=2), nullable=False),
        sa.Column("changed_by", sa.Integer(), sa.ForeignKey("dosen.id"), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
    )
    op.create_index("ix_grade_history_grade_id", "grade_history", ["grade_id"])

    # 4. Buat SQL view riwayat perubahan nilai per mahasiswa
    op.execute("DROP VIEW IF EXISTS v_riwayat_nilai")
    op.execute(VIEW_RIWAYAT_NILAI_SQL)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_riwayat_nilai")
    op.drop_index("ix_grade_history_grade_id", table_name="grade_history")
    op.drop_table("grade_history")

    with op.batch_alter_table("krs_detail") as batch_op:
        batch_op.drop_constraint("fk_krs_detail_nilai_skala_nilai", type_="foreignkey")

    with op.batch_alter_table("skala_nilai") as batch_op:
        batch_op.drop_column("lulus")
        batch_op.alter_column(
            "bobot",
            existing_type=sa.Numeric(3, 2),
            type_=sa.Float(),
            existing_nullable=False,
        )
