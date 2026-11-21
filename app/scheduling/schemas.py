"""Skema Pydantic untuk API penjadwalan, konflik, saran AI, outbox, dan KRS."""

from __future__ import annotations

from datetime import datetime, time
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class JadwalIn(BaseModel):
    kelas_id: int
    hari: int = Field(ge=1, le=6)
    jam_mulai: time
    jam_selesai: time
    ruangan_kode: str = Field(min_length=1)
    dosen_id: int

    @model_validator(mode="after")
    def _cek_urutan_jam(self) -> "JadwalIn":
        if self.jam_mulai >= self.jam_selesai:
            raise ValueError("jam_mulai harus lebih awal dari jam_selesai")
        return self


class JadwalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kelas_id: int
    nama_kelas: str = ""
    hari: int
    jam_mulai: time
    jam_selesai: time
    ruangan_kode: str
    kapasitas_ruangan: int = 0
    dosen_id: int
    nama_dosen: str = ""
    kuota_kelas: int = 0
    terdaftar: int = 0
    sequence: int = 0


class ConflictOut(BaseModel):
    type: str
    affected: tuple[int, int]
    detail: str = ""
    schedules: list[dict[str, Any]] = Field(default_factory=list)


class Saran(BaseModel):
    """Model Pydantic Saringan 2 untuk output AI-powered rescheduling."""

    hari: int = Field(ge=1, le=6)
    jam_mulai: time
    ruangan: str = Field(min_length=1)
    reason: str = ""


class OutboxOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: str
    status: str
    attempts: int
    payload: dict[str, Any]
    created_at: datetime


class KRSOut(BaseModel):
    id: int
    nim: str
    nama_mahasiswa: str
    semester: str
    status: str
    catatan_revisi: str | None
    kelas_ids: list[int]
    mata_kuliah: list[str]
