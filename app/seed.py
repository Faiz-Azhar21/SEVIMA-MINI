"""Helper untuk mengisi data master awal (Program Studi & Jalur Masuk)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import JalurMasuk, ProgramStudi

DEFAULT_PRODI = [
    {"kode": "001", "nama": "Teknik Informatika", "fakultas": "Fakultas Ilmu Komputer"},
    {"kode": "002", "nama": "Sistem Informasi", "fakultas": "Fakultas Ilmu Komputer"},
    {"kode": "003", "nama": "Teknik Elektro", "fakultas": "Fakultas Teknik"},
]

DEFAULT_JALUR = [
    {"kode": "SNBP", "nama": "Seleksi Nasional Berdasarkan Prestasi", "deskripsi": "Jalur prestasi akademik"},
    {"kode": "SNBT", "nama": "Seleksi Nasional Berdasarkan Tes", "deskripsi": "Jalur ujian tulis nasional"},
    {"kode": "Mandiri", "nama": "Seleksi Mandiri", "deskripsi": "Jalur seleksi internal perguruan tinggi"},
]


def seed_master_data(db: Session) -> None:
    """Menyisipkan data master ProgramStudi dan JalurMasuk secara idempotent."""
    for item in DEFAULT_PRODI:
        exists = db.scalars(
            select(ProgramStudi).where(ProgramStudi.kode == item["kode"])
        ).one_or_none()
        if exists is None:
            db.add(ProgramStudi(**item))

    for item in DEFAULT_JALUR:
        exists = db.scalars(
            select(JalurMasuk).where(JalurMasuk.kode == item["kode"])
        ).one_or_none()
        if exists is None:
            db.add(JalurMasuk(**item))

    db.commit()


if __name__ == "__main__":  # pragma: no cover
    with SessionLocal() as session:
        seed_master_data(session)
        print("Data master ProgramStudi dan JalurMasuk berhasil di-seed.")
