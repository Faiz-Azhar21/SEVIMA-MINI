"""Skema Pydantic v2 untuk validasi input/output API Jadwal & Ruangan."""

from __future__ import annotations

from datetime import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ConflictType = Literal["room_conflict", "lecturer_conflict"]


class JadwalIn(BaseModel):
    """Payload input untuk membuat atau memperbarui jadwal kuliah."""

    kelas_id: int
    hari: int = Field(ge=1, le=6, description="1 = Senin .. 6 = Sabtu")
    jam_mulai: time  # otomatis parsing "08:00" -> time(8, 0)
    jam_selesai: time
    ruangan_kode: str = Field(min_length=1, max_length=20)
    dosen_id: int

    @model_validator(mode="after")
    def jam_urutan(self) -> JadwalIn:
        if self.jam_mulai >= self.jam_selesai:
            raise ValueError("jam_mulai harus sebelum jam_selesai")
        return self


class JadwalOut(BaseModel):
    """Representasi jadwal yang dikembalikan oleh API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    kelas_id: int
    hari: int
    jam_mulai: time
    jam_selesai: time
    ruangan_kode: str
    dosen_id: int


class ConflictOut(BaseModel):
    """Representasi satu pasangan/entitas bentrok jadwal."""

    type: ConflictType
    affected: list[int]
