"""Model domain Modul Jadwal & Ruangan (SQLAlchemy 2.0)."""

from __future__ import annotations

from datetime import time

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Time
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Ruangan(Base):
    """Ruang kuliah atau laboratorium dengan kode sebagai primary key alami."""

    __tablename__ = "ruangan"

    kode: Mapped[str] = mapped_column(String(20), primary_key=True)  # contoh: "A101"
    nama: Mapped[str] = mapped_column(String(100))
    kapasitas: Mapped[int]


class Dosen(Base):
    """Dosen pengampu kelas dengan NIDN unik."""

    __tablename__ = "dosen"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nidn: Mapped[str] = mapped_column(String(20), unique=True)
    nama: Mapped[str] = mapped_column(String(100))


class Kelas(Base):
    """Kelas paralel dari sebuah mata kuliah pada semester tertentu (mis. Basis Data A, B)."""

    __tablename__ = "kelas"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    kode_mk: Mapped[str] = mapped_column(ForeignKey("matakuliah.kode_mk"))
    nama_kelas: Mapped[str] = mapped_column(String(10))
    kuota: Mapped[int]
    semester: Mapped[str] = mapped_column(String(10))  # contoh: "20251"


class Jadwal(Base):
    """Satu pertemuan mingguan yang mengikat kelas, waktu, ruangan, dan dosen."""

    __tablename__ = "jadwal"
    __table_args__ = (
        CheckConstraint("jam_mulai < jam_selesai", name="ck_jadwal_jam_valid"),
        CheckConstraint("hari BETWEEN 1 AND 6", name="ck_jadwal_hari_valid"),
        Index("ix_jadwal_ruangan", "hari", "ruangan_kode"),
        Index("ix_jadwal_dosen", "hari", "dosen_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    kelas_id: Mapped[int] = mapped_column(ForeignKey("kelas.id"))
    hari: Mapped[int]  # 1 = Senin .. 6 = Sabtu
    jam_mulai: Mapped[time] = mapped_column(Time)  # time, BUKAN str
    jam_selesai: Mapped[time] = mapped_column(Time)
    ruangan_kode: Mapped[str] = mapped_column(ForeignKey("ruangan.kode"))
    dosen_id: Mapped[int] = mapped_column(ForeignKey("dosen.id"))
