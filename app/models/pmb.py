"""Model minimal dari Modul PMB (Minggu 3-4) sebagai induk FK krs.nim."""

from __future__ import annotations

import enum

from sqlalchemy import Enum as SAEnum
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PMBStatus(str, enum.Enum):
    """Status pendaftaran calon mahasiswa dari Modul PMB."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class CalonMahasiswa(Base):
    """Tabel calon_mahasiswa dari Modul PMB.

    Kolom `nim` bersifat UNIQUE dan nullable (hanya terisi setelah di-approve).
    Menjadi target ForeignKey dari `krs.nim`.
    """

    __tablename__ = "calon_mahasiswa"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nama: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    prodi: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[PMBStatus] = mapped_column(
        SAEnum(PMBStatus, native_enum=False, length=20),
        default=PMBStatus.PENDING,
        nullable=False,
    )
    nim: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)

    def __repr__(self) -> str:
        return f"<CalonMahasiswa(id={self.id}, nama={self.nama!r}, nim={self.nim!r})>"
