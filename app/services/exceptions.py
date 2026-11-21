"""Hierarki exception polimorfik untuk lapisan SchedulingService dan API."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from app.services.conflict import Conflict


class ScheduleError(Exception):
    """Base exception untuk seluruh error domain penjadwalan."""

    status_code: int = 400

    def body(self) -> dict[str, Any]:
        return {"detail": str(self)}


class NotFoundError(ScheduleError):
    """Entitas (jadwal, ruangan, dosen, atau kelas) tidak ditemukan."""

    status_code: int = 404


class CapacityError(ScheduleError):
    """Jumlah peserta (max(kuota, terdaftar)) melebihi kapasitas ruangan."""

    status_code: int = 409


class ScheduleConflictError(ScheduleError):
    """Jadwal baru/diubah bentrok dengan jadwal lain di ruangan atau dosen yang sama."""

    status_code: int = 409

    def __init__(self, konflik: list[Conflict]) -> None:
        super().__init__(f"Jadwal bentrok ({len(konflik)} konflik)")
        self.konflik = konflik

    def body(self) -> dict[str, Any]:
        return super().body() | {
            "conflicts": [
                {"type": k.type, "affected": list(k.affected)} for k in self.konflik
            ]
        }
