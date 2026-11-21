"""Model ORM akademik (kelanjutan Minggu 5-8) untuk SEVIMA-Mini."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.nilai import GradeHistory, SkalaNilai


class Mahasiswa(Base):
    __tablename__ = "mahasiswa"

    nim: Mapped[str] = mapped_column(String(20), primary_key=True)
    nama: Mapped[str] = mapped_column(String(120), nullable=False)
    prodi: Mapped[str] = mapped_column(String(100), nullable=False)
    angkatan: Mapped[int] = mapped_column(Integer, nullable=False)

    krs_list: Mapped[list[KRS]] = relationship(back_populates="mahasiswa")


class Dosen(Base):
    __tablename__ = "dosen"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nidn: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    nama: Mapped[str] = mapped_column(String(120), nullable=False)

    jadwal_list: Mapped[list[Jadwal]] = relationship(back_populates="dosen")


class MataKuliah(Base):
    __tablename__ = "matakuliah"

    kode_mk: Mapped[str] = mapped_column(String(20), primary_key=True)
    nama_mk: Mapped[str] = mapped_column(String(150), nullable=False)
    sks: Mapped[int] = mapped_column(Integer, nullable=False)


class Kelas(Base):
    __tablename__ = "kelas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kode_mk: Mapped[str] = mapped_column(String(20), ForeignKey("matakuliah.kode_mk"), nullable=False)
    nama_kelas: Mapped[str] = mapped_column(String(50), nullable=False)
    semester: Mapped[str] = mapped_column(String(10), nullable=False)

    matakuliah: Mapped[MataKuliah] = relationship()
    jadwal_list: Mapped[list[Jadwal]] = relationship(back_populates="kelas")


class Jadwal(Base):
    """Model Jadwal dari Minggu 7 — mengikat dosen pengampu ke kelas."""

    __tablename__ = "jadwal"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kelas_id: Mapped[int] = mapped_column(Integer, ForeignKey("kelas.id"), nullable=False, index=True)
    dosen_id: Mapped[int] = mapped_column(Integer, ForeignKey("dosen.id"), nullable=False, index=True)
    ruangan: Mapped[str] = mapped_column(String(50), nullable=False, default="R-101")
    hari: Mapped[str] = mapped_column(String(20), nullable=False, default="Senin")
    jam_mulai: Mapped[str] = mapped_column(String(5), nullable=False, default="08:00")
    jam_selesai: Mapped[str] = mapped_column(String(5), nullable=False, default="10:00")

    kelas: Mapped[Kelas] = relationship(back_populates="jadwal_list")
    dosen: Mapped[Dosen] = relationship(back_populates="jadwal_list")


class KRS(Base):
    __tablename__ = "krs"
    __table_args__ = (UniqueConstraint("nim", "semester", name="uq_krs_nim_semester"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nim: Mapped[str] = mapped_column(String(20), ForeignKey("mahasiswa.nim"), nullable=False, index=True)
    semester: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="APPROVED")

    mahasiswa: Mapped[Mahasiswa] = relationship(back_populates="krs_list")
    details: Mapped[list[KRSDetail]] = relationship(back_populates="krs")


class KRSDetail(Base):
    """Satu grade = satu baris krs_detail (Minggu 5 -> 7 -> 9)."""

    __tablename__ = "krs_detail"
    __table_args__ = (UniqueConstraint("krs_id", "kelas_id", name="uq_krs_detail_krs_kelas"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    krs_id: Mapped[int] = mapped_column(Integer, ForeignKey("krs.id"), nullable=False, index=True)
    kode_mk: Mapped[str] = mapped_column(String(20), ForeignKey("matakuliah.kode_mk"), nullable=False)
    kelas_id: Mapped[int] = mapped_column(Integer, ForeignKey("kelas.id"), nullable=False, index=True)
    # Minggu 9: kolom nilai kini menjadi Foreign Key ke skala_nilai.huruf
    nilai: Mapped[str | None] = mapped_column(
        String(2),
        ForeignKey("skala_nilai.huruf"),
        nullable=True,
    )

    krs: Mapped[KRS] = relationship(back_populates="details")
    matakuliah: Mapped[MataKuliah] = relationship()
    kelas: Mapped[Kelas] = relationship()
    skala_nilai: Mapped[SkalaNilai | None] = relationship()
    history: Mapped[list[GradeHistory]] = relationship(back_populates="grade")
