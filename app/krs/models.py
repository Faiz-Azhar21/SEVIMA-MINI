"""Model domain KRS dan state machine transisi status.

Diperluas di Minggu 8 dengan ``Actor.SISTEM`` serta dua transisi resmi:
- ``(SUBMITTED, SISTEM) -> REVISION``
- ``(APPROVED, SISTEM) -> REVISION``
sehingga total matriks 4 x 4 x 3 = 48 kombinasi terdiri dari 6 transisi sah
dan 42 transisi ilegal.
"""

from __future__ import annotations

from enum import Enum

from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class KRSStatus(str, Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    REVISION = "REVISION"


class Actor(str, Enum):
    MAHASISWA = "MAHASISWA"
    DOSEN_PA = "DOSEN_PA"
    SISTEM = "SISTEM"  # Baru di Minggu 8 untuk invalidasi otomatis saat jadwal berubah


# Peta transisi resmi state machine KRS (6 kombinasi sah dari 4 x 4 x 3 = 48)
TRANSITIONS: dict[tuple[KRSStatus, Actor], set[KRSStatus]] = {
    # 4 transisi Minggu 6
    (KRSStatus.DRAFT, Actor.MAHASISWA): {KRSStatus.SUBMITTED},
    (KRSStatus.REVISION, Actor.MAHASISWA): {KRSStatus.SUBMITTED},
    (KRSStatus.SUBMITTED, Actor.DOSEN_PA): {KRSStatus.APPROVED, KRSStatus.REVISION},
    # 2 transisi Minggu 8 (invalidasi otomatis oleh sistem)
    (KRSStatus.SUBMITTED, Actor.SISTEM): {KRSStatus.REVISION},
    (KRSStatus.APPROVED, Actor.SISTEM): {KRSStatus.REVISION},
}


class IllegalKRSTransitionError(ValueError):
    """Dilempar saat terjadi percobaan transisi status KRS yang tidak diizinkan."""

    def __init__(self, current: KRSStatus, target: KRSStatus, actor: Actor) -> None:
        self.current = current
        self.target = target
        self.actor = actor
        super().__init__(
            f"Transisi KRS ilegal: {current.value} -> {target.value} oleh {actor.value}"
        )


class Mahasiswa(Base):
    __tablename__ = "mahasiswa"

    nim: Mapped[str] = mapped_column(String(20), primary_key=True)
    nama: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(150))

    krs_list: Mapped[list["KRS"]] = relationship(back_populates="mahasiswa")


class KRS(Base):
    __tablename__ = "krs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nim: Mapped[str] = mapped_column(ForeignKey("mahasiswa.nim"), index=True)
    semester: Mapped[str] = mapped_column(String(20), default="2026/2027-Ganjil")
    status: Mapped[KRSStatus] = mapped_column(
        SQLEnum(KRSStatus, native_enum=False), default=KRSStatus.DRAFT
    )
    catatan_revisi: Mapped[str | None] = mapped_column(String(255), nullable=True)

    mahasiswa: Mapped[Mahasiswa] = relationship(back_populates="krs_list")
    details: Mapped[list["KRSDetail"]] = relationship(
        back_populates="krs", cascade="all, delete-orphan"
    )

    def transition(self, target: KRSStatus, actor: Actor) -> None:
        """Satu-satunya pintu resmi untuk mengubah status KRS."""
        allowed = TRANSITIONS.get((self.status, actor), set())
        if target not in allowed:
            raise IllegalKRSTransitionError(self.status, target, actor)
        self.status = target


class KRSDetail(Base):
    __tablename__ = "krs_detail"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    krs_id: Mapped[int] = mapped_column(ForeignKey("krs.id"), index=True)
    kelas_id: Mapped[int] = mapped_column(ForeignKey("kelas.id"), index=True)
    nilai: Mapped[str | None] = mapped_column(String(5), nullable=True)  # Diisi di Materi 5

    krs: Mapped[KRS] = relationship(back_populates="details")
