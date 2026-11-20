"""Pydantic v2 request/response schemas untuk endpoint Modul KRS."""

from __future__ import annotations

from datetime import time

from pydantic import BaseModel, ConfigDict, Field

from app.models.krs import KRSStatus


class AddCourseRequest(BaseModel):
    """Payload permintaan tambah mata kuliah ke KRS."""

    kode_mk: str = Field(..., min_length=2, max_length=10, examples=["IF201"])


class MataKuliahOut(BaseModel):
    """Representasi ringkas mata kuliah pada response KRS."""

    model_config = ConfigDict(from_attributes=True)

    kode_mk: str
    nama: str
    sks: int
    hari: int
    jam_mulai: time
    jam_selesai: time


class KRSDetailOut(BaseModel):
    """Representasi satu item mata kuliah dalam KRS."""

    id: int
    kode_mk: str
    nilai: str | None
    matakuliah: MataKuliahOut


class KRSOut(BaseModel):
    """Representasi satu kartu KRS beserta total SKS."""

    id: int
    nim: str
    semester: str
    status: KRSStatus
    dosen_pa_id: int | None
    total_sks: int
    details: list[KRSDetailOut]


class ValidationIssueOut(BaseModel):
    """Satu pelanggaran hasil validasi menyeluruh KRS."""

    ok: bool
    message: str


class KRSValidationOut(BaseModel):
    """Response validasi menyeluruh KRS (`validate_krs`)."""

    nim: str
    semester: str
    valid: bool
    issues: list[ValidationIssueOut]


class MessageOut(BaseModel):
    """Response pesan sederhana."""

    message: str
