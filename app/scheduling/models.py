"""Model ORM penjadwalan (Ruangan, Dosen, Kelas, Jadwal) dan tabel Transactional Outbox."""

from __future__ import annotations

from datetime import datetime, time, timezone
from typing import Any

from sqlalchemy import ForeignKey, JSON, String, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.scheduling.observer import EventType, ScheduleEvent


class Ruangan(Base):
    __tablename__ = "ruangan"

    kode: Mapped[str] = mapped_column(String(20), primary_key=True)
    nama: Mapped[str] = mapped_column(String(100))
    kapasitas: Mapped[int] = mapped_column()


class Dosen(Base):
    __tablename__ = "dosen"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nidn: Mapped[str] = mapped_column(String(30), unique=True)
    nama: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(150))


class Kelas(Base):
    __tablename__ = "kelas"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    kode_mk: Mapped[str] = mapped_column(String(20))
    nama: Mapped[str] = mapped_column(String(120))
    kuota: Mapped[int] = mapped_column(default=40)
    semester: Mapped[str] = mapped_column(String(20), default="2026/2027-Ganjil")


class Jadwal(Base):
    __tablename__ = "jadwal"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    kelas_id: Mapped[int] = mapped_column(ForeignKey("kelas.id"), index=True)
    hari: Mapped[int] = mapped_column()  # 1=Senin .. 6=Sabtu
    jam_mulai: Mapped[time] = mapped_column(Time)
    jam_selesai: Mapped[time] = mapped_column(Time)
    ruangan_kode: Mapped[str] = mapped_column(ForeignKey("ruangan.kode"), index=True)
    dosen_id: Mapped[int] = mapped_column(ForeignKey("dosen.id"), index=True)
    sequence: Mapped[int] = mapped_column(default=0)  # Naik tiap jadwal berubah (untuk .ics)

    kelas: Mapped[Kelas] = relationship()
    ruangan: Mapped[Ruangan] = relationship()
    dosen: Mapped[Dosen] = relationship()


class Outbox(Base):
    """Tabel Transactional Outbox untuk memastikan event ditulis atomik bersama perubahan jadwal."""

    __tablename__ = "outbox"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)
    attempts: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc)
    )

    @classmethod
    def dari_event(cls, e: ScheduleEvent) -> "Outbox":
        return cls(
            event_id=e.event_id,
            payload={
                "type": e.event_type.value,
                "jadwal_id": e.jadwal_id,
                "before": e.before,
                "after": e.after,
            },
        )

    def ke_event(self) -> ScheduleEvent:
        p = self.payload
        return ScheduleEvent(
            event_type=EventType(p["type"]),
            jadwal_id=p["jadwal_id"],
            before=p.get("before"),
            after=p.get("after"),
            event_id=self.event_id,
        )
