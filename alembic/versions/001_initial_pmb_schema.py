"""Initial PMB Schema with rollback

Revision ID: 001_initial_pmb
Revises: 
Create Date: 2026-11-19 19:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '001_initial_pmb'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Tabel program_studi
    op.create_table(
        'program_studi',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('kode', sa.String(length=3), nullable=False),
        sa.Column('nama', sa.String(length=100), nullable=False),
        sa.Column('fakultas', sa.String(length=100), nullable=False),
    )
    op.create_index(op.f('ix_program_studi_id'), 'program_studi', ['id'], unique=False)
    op.create_index(op.f('ix_program_studi_kode'), 'program_studi', ['kode'], unique=True)

    # 2. Tabel jalur_masuk
    op.create_table(
        'jalur_masuk',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('kode', sa.String(length=20), nullable=False),
        sa.Column('nama', sa.String(length=100), nullable=False),
        sa.Column('keterangan', sa.String(length=255), nullable=True),
    )
    op.create_index(op.f('ix_jalur_masuk_id'), 'jalur_masuk', ['id'], unique=False)
    op.create_index(op.f('ix_jalur_masuk_kode'), 'jalur_masuk', ['kode'], unique=True)

    # 3. Tabel calon_mahasiswa dengan constraint
    op.create_table(
        'calon_mahasiswa',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('nama_lengkap', sa.String(length=150), nullable=False),
        sa.Column('email', sa.String(length=150), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=False),
        sa.Column('tanggal_lahir', sa.Date(), nullable=False),
        sa.Column('alamat', sa.Text(), nullable=False),
        sa.Column('program_studi_id', sa.Integer(), sa.ForeignKey('program_studi.id'), nullable=False),
        sa.Column('jalur_masuk_id', sa.Integer(), sa.ForeignKey('jalur_masuk.id'), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('nim', sa.String(length=20), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.CheckConstraint("(phone LIKE '08%') OR (phone LIKE '+62%') OR (phone LIKE '62%')", name='check_phone_indonesia'),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected')", name='check_status_enum')
    )
    op.create_index(op.f('ix_calon_mahasiswa_id'), 'calon_mahasiswa', ['id'], unique=False)
    op.create_index(op.f('ix_calon_mahasiswa_email'), 'calon_mahasiswa', ['email'], unique=True)
    op.create_index(op.f('ix_calon_mahasiswa_nim'), 'calon_mahasiswa', ['nim'], unique=True)

    # Seed data program studi
    op.bulk_insert(
        sa.table(
            'program_studi',
            sa.column('id', sa.Integer),
            sa.column('kode', sa.String),
            sa.column('nama', sa.String),
            sa.column('fakultas', sa.String),
        ),
        [
            {'id': 1, 'kode': '001', 'nama': 'Teknik Informatika', 'fakultas': 'Fakultas Ilmu Komputer'},
            {'id': 2, 'kode': '002', 'nama': 'Sistem Informasi', 'fakultas': 'Fakultas Ilmu Komputer'},
            {'id': 3, 'kode': '003', 'nama': 'Teknik Komputer', 'fakultas': 'Fakultas Teknik'},
        ]
    )

    # Seed data jalur masuk
    op.bulk_insert(
        sa.table(
            'jalur_masuk',
            sa.column('id', sa.Integer),
            sa.column('kode', sa.String),
            sa.column('nama', sa.String),
            sa.column('keterangan', sa.String),
        ),
        [
            {'id': 1, 'kode': 'SNBP', 'nama': 'Seleksi Nasional Berdasarkan Prestasi', 'keterangan': 'Jalur rapor prestasi'},
            {'id': 2, 'kode': 'SNBT', 'nama': 'Seleksi Nasional Berdasarkan Tes', 'keterangan': 'Jalur ujian UTBK'},
            {'id': 3, 'kode': 'Mandiri', 'nama': 'Seleksi Mandiri', 'keterangan': 'Jalur mandiri institusi'},
        ]
    )


def downgrade() -> None:
    # Rollback urutan: calon_mahasiswa -> jalur_masuk -> program_studi
    op.drop_index(op.f('ix_calon_mahasiswa_nim'), table_name='calon_mahasiswa')
    op.drop_index(op.f('ix_calon_mahasiswa_email'), table_name='calon_mahasiswa')
    op.drop_index(op.f('ix_calon_mahasiswa_id'), table_name='calon_mahasiswa')
    op.drop_table('calon_mahasiswa')

    op.drop_index(op.f('ix_jalur_masuk_kode'), table_name='jalur_masuk')
    op.drop_index(op.f('ix_jalur_masuk_id'), table_name='jalur_masuk')
    op.drop_table('jalur_masuk')

    op.drop_index(op.f('ix_program_studi_kode'), table_name='program_studi')
    op.drop_index(op.f('ix_program_studi_id'), table_name='program_studi')
    op.drop_table('program_studi')
