"""Pydantic schemas untuk request dan response API Modul KRS."""

from datetime import datetime, time
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.enums import JenisMK, KRSStatus


class AddCourseRequest(BaseModel):
    kode_mk: str = Field(..., min_length=1, examples=["IF201"])


class ApproveKRSRequest(BaseModel):
    dosen_pa_id: int = Field(..., ge=1)
    version: Optional[int] = Field(
        default=None,
        ge=1,
        description="Versi KRS yang dilihat dosen (untuk deteksi layar basi / optimistic lock)",
    )


class ReviseKRSRequest(BaseModel):
    dosen_pa_id: int = Field(..., ge=1)
    catatan: str = Field(..., min_length=1, description="Catatan revisi wajib diisi")
    version: Optional[int] = Field(default=None, ge=1)

    @field_validator("catatan")
    @classmethod
    def catatan_tidak_boleh_kosong(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Catatan revisi wajib diisi")
        return value.strip()


class MatakuliahResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kode_mk: str
    kode_induk: str
    kelas: str
    nama: str
    sks: int
    hari: int
    jam_mulai: time
    jam_selesai: time
    jenis: JenisMK


class KRSDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kode_mk: str
    matakuliah: MatakuliahResponse


class KRSResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nim: str
    semester: int
    dosen_pa_id: int
    status: KRSStatus
    total_sks: int
    version: int
    submitted_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    catatan_revisi: Optional[str] = None
    details: list[KRSDetailResponse] = []


class ValidationResponse(BaseModel):
    valid: bool
    errors: list[str] = []


class RecommendRequest(BaseModel):
    desired_courses: list[str] = Field(
        ...,
        min_length=1,
        description="Daftar kode MK atau kode MK induk yang ingin diambil mahasiswa",
    )
    max_sks: int = Field(default=24, ge=1, le=24)
    target_sks: int = Field(default=20, ge=1, le=24)


class RecommendResponse(BaseModel):
    selected_courses: list[MatakuliahResponse]
    total_sks: int
    wajib_count: int
    pilihan_count: int
    skipped_courses: dict[str, str]
    validated: bool
    tool_trace: list[str]
