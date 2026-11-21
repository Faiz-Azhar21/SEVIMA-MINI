"""Model baseline dari Materi 3 (Modul KRS) yang berelasi dengan Modul Jadwal."""

from __future__ import annotations

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MataKuliah(Base):
    """Tabel mata kuliah (kolom hari & jam sudah dipindah ke tabel jadwal via migration)."""

    __tablename__ = "matakuliah"

    kode_mk: Mapped[str] = mapped_column(String(20), primary_key=True)
    nama: Mapped[str] = mapped_column(String(100))
    sks: Mapped[int]


class KRS(Base):
    """Header Kartu Rencana Studi mahasiswa per semester."""

    __tablename__ = "krs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nim: Mapped[str] = mapped_column(String(20), index=True)
    semester: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")


class KRSDetail(Base):
    """Detail kelas/mata kuliah yang diambil mahasiswa pada KRS.

    Kolom ``kelas_id`` ditambahkan pada Minggu 7 untuk menghitung jumlah peserta
    terdaftar; integrasi penuh (invalidasi KRS saat jadwal berubah) diselesaikan di Minggu 8.
    """

    __tablename__ = "krs_detail"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    krs_id: Mapped[int] = mapped_column(ForeignKey("krs.id", ondelete="CASCADE"))
    kode_mk: Mapped[str] = mapped_column(ForeignKey("matakuliah.kode_mk"))
    kelas_id: Mapped[int | None] = mapped_column(ForeignKey("kelas.id"), nullable=True)
