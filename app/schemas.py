"""Skema Pydantic v2 untuk validasi input dan pemfilteran output API PMB."""

from __future__ import annotations

import re
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import JalurMasukEnum, StatusPMB

INDONESIA_PHONE_REGEX = re.compile(r"^(?:\+62|62|0)8[1-9][0-9]{7,11}$")


def validate_indonesian_phone(phone: str) -> str:
    """Validasi nomor telepon seluler Indonesia (08..., 628..., atau +628..., 10-15 char)."""
    cleaned = phone.strip()
    if not (10 <= len(cleaned) <= 15) or not INDONESIA_PHONE_REGEX.fullmatch(cleaned):
        raise ValueError(
            "Format nomor telepon Indonesia tidak valid. "
            "Gunakan awalan 08, 628, atau +628 (10-15 karakter, hanya angka)."
        )
    return cleaned


class RegisterIn(BaseModel):
    """Payload pendaftaran calon mahasiswa baru."""

    nama_lengkap: str = Field(..., min_length=2, max_length=150, examples=["Sinta Dewi"])
    email: EmailStr = Field(..., examples=["sinta@mail.com"])
    phone: str = Field(..., examples=["081234567890"])
    tanggal_lahir: date = Field(..., examples=["2006-05-14"])
    alamat: str = Field(..., min_length=5, max_length=500, examples=["Jl. Merdeka No. 10, Surabaya"])
    program_studi_id: int = Field(..., gt=0, examples=[1])
    jalur_masuk: JalurMasukEnum = Field(..., examples=["SNBP"])

    @field_validator("nama_lengkap", "alamat")
    @classmethod
    def strip_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Field tidak boleh kosong")
        return cleaned

    @field_validator("phone")
    @classmethod
    def check_phone(cls, value: str) -> str:
        return validate_indonesian_phone(value)

    @field_validator("tanggal_lahir")
    @classmethod
    def check_tanggal_lahir(cls, value: date) -> date:
        if value >= date.today():
            raise ValueError("Tanggal lahir harus sebelum hari ini")
        return value


class RegisterOut(BaseModel):
    """Respons setelah registrasi berhasil (HTTP 201)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    nama_lengkap: str
    email: EmailStr
    phone: str
    tanggal_lahir: date
    alamat: str
    program_studi_id: int
    jalur_masuk: str
    status: StatusPMB
    created_at: datetime


class StatusOut(BaseModel):
    """Skema output terfilter untuk cek status pendaftar (tanpa data pribadi sensitif)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    nama_lengkap: str
    program_studi_id: int
    jalur_masuk: str
    status: StatusPMB
    nim: str | None = None
    approved_at: datetime | None = None


class ApproveOut(BaseModel):
    """Respons hasil persetujuan pendaftar beserta NIM yang dihasilkan."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    nama_lengkap: str
    nim: str
    status: StatusPMB
    approved_at: datetime


class RejectOut(BaseModel):
    """Respons hasil penolakan pendaftar."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    nama_lengkap: str
    status: StatusPMB


class StatsOut(BaseModel):
    """Respons dashboard statistik jumlah pendaftar PMB."""

    total: int
    per_status: dict[str, int]
    per_prodi: dict[str, int]
    per_jalur_masuk: dict[str, int]
