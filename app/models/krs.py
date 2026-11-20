"""Model ORM SQLAlchemy 2.0 untuk Modul KRS (Kartu Rencana Studi).

Mencakup 4 tabel utama sesuai deliverable + 1 tabel bantu skala_nilai:
1. matakuliah
2. prerequisite (self-referencing many-to-many pada matakuliah)
3. krs (header kartu per mahasiswa per semester)
4. krs_detail (baris mata kuliah di dalam kartu KRS + nilai)
5. skala_nilai (pemetaan nilai huruf ke bobot numerik)
"""

from __future__ import annotations

import enum
from datetime import time

from sqlalchemy import (
    CheckConstraint,
    Column,
    Enum as SAEnum,
    ForeignKey,
    Numeric,
    String,
    Table,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class KRSStatus(str, enum.Enum):
    """Status siklus hidup KRS (transisi state machine penuh di Minggu 6)."""

    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    REVISION = "REVISION"


prerequisite = Table(
    "prerequisite",
    Base.metadata,
    Column(
        "kode_mk",
        String(10),
        ForeignKey("matakuliah.kode_mk", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "kode_prasyarat",
        String(10),
        ForeignKey("matakuliah.kode_mk", ondelete="CASCADE"),
        primary_key=True,
    ),
    CheckConstraint("kode_mk <> kode_prasyarat", name="ck_prerequisite_not_self"),
)


class SkalaNilai(Base):
    """Pemetaan nilai huruf (A..E) ke bobot angka untuk mencegah bug perbandingan string."""

    __tablename__ = "skala_nilai"

    huruf: Mapped[str] = mapped_column(String(2), primary_key=True)
    bobot: Mapped[float] = mapped_column(Numeric(3, 2), nullable=False)

    def __repr__(self) -> str:
        return f"<SkalaNilai(huruf={self.huruf!r}, bobot={self.bobot})>"


class MataKuliah(Base):
    """Master mata kuliah beserta jadwal (asumsi 1 MK = 1 kelas pada Minggu 5-6)."""

    __tablename__ = "matakuliah"
    __table_args__ = (
        CheckConstraint("sks BETWEEN 1 AND 4", name="ck_matakuliah_sks_range"),
        CheckConstraint("hari BETWEEN 1 AND 6", name="ck_matakuliah_hari_range"),
        CheckConstraint("jam_mulai < jam_selesai", name="ck_matakuliah_jam_valid"),
    )

    kode_mk: Mapped[str] = mapped_column(String(10), primary_key=True)
    nama: Mapped[str] = mapped_column(String(100), nullable=False)
    sks: Mapped[int] = mapped_column(nullable=False)
    hari: Mapped[int] = mapped_column(nullable=False)  # 1 = Senin .. 6 = Sabtu
    jam_mulai: Mapped[time] = mapped_column(Time, nullable=False)
    jam_selesai: Mapped[time] = mapped_column(Time, nullable=False)

    # Self-referencing many-to-many:
    # primaryjoin: MK ini -> prerequisite.kode_mk
    # secondaryjoin: prerequisite.kode_prasyarat -> MK prasyaratnya
    prasyarat: Mapped[list["MataKuliah"]] = relationship(
        "MataKuliah",
        secondary=prerequisite,
        primaryjoin=kode_mk == prerequisite.c.kode_mk,
        secondaryjoin=kode_mk == prerequisite.c.kode_prasyarat,
    )

    def __repr__(self) -> str:
        return f"<MataKuliah(kode_mk={self.kode_mk!r}, nama={self.nama!r}, sks={self.sks})>"


class KRS(Base):
    """Header satu kartu KRS milik satu mahasiswa pada satu semester."""

    __tablename__ = "krs"
    __table_args__ = (
        UniqueConstraint("nim", "semester", name="uq_krs_nim_semester"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nim: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("calon_mahasiswa.nim", ondelete="RESTRICT"),
        nullable=False,
    )
    semester: Mapped[str] = mapped_column(String(5), nullable=False)  # mis. "20251"
    status: Mapped[KRSStatus] = mapped_column(
        SAEnum(KRSStatus, native_enum=False, length=20),
        default=KRSStatus.DRAFT,
        nullable=False,
    )
    dosen_pa_id: Mapped[int | None] = mapped_column(nullable=True)

    details: Mapped[list["KRSDetail"]] = relationship(
        back_populates="krs",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<KRS(id={self.id}, nim={self.nim!r}, semester={self.semester!r}, status={self.status.value})>"


class KRSDetail(Base):
    """Baris mata kuliah di dalam kartu KRS beserta nilai (NULL sampai semester selesai)."""

    __tablename__ = "krs_detail"
    __table_args__ = (
        UniqueConstraint("krs_id", "kode_mk", name="uq_krs_detail_krs_mk"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    krs_id: Mapped[int] = mapped_column(
        ForeignKey("krs.id", ondelete="CASCADE"),
        nullable=False,
    )
    kode_mk: Mapped[str] = mapped_column(
        String(10),
        ForeignKey("matakuliah.kode_mk", ondelete="RESTRICT"),
        nullable=False,
    )
    nilai: Mapped[str | None] = mapped_column(
        String(2),
        ForeignKey("skala_nilai.huruf", ondelete="RESTRICT"),
        nullable=True,
    )

    krs: Mapped["KRS"] = relationship(back_populates="details")
    matakuliah: Mapped["MataKuliah"] = relationship()

    def __repr__(self) -> str:
        return f"<KRSDetail(id={self.id}, krs_id={self.krs_id}, kode_mk={self.kode_mk!r}, nilai={self.nilai!r})>"
