"""Pydantic schemas untuk request dan response API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class GenerateBillingRequest(BaseModel):
    semester: str = Field(..., examples=["2026/2027-Ganjil"])
    semester_start: date = Field(..., examples=["2026-09-01"])


class ManualPaymentRequest(BaseModel):
    billing_id: int = Field(..., gt=0)
    amount: int = Field(..., gt=0)
    method: str = Field(..., examples=["TRANSFER_MANUAL", "CASH_LOKET", "VA_BCA"])
    transaction_id: str | None = Field(default=None)
    notes: str | None = Field(default=None)


class WebhookPaymentPayload(BaseModel):
    transaction_id: str = Field(..., min_length=3, examples=["GW-TRX-20261123-001"])
    billing_id: int | None = Field(default=None, gt=0)
    billing_code: str | None = Field(default=None, examples=["INV-2026G1-2401001"])
    amount: int = Field(..., gt=0)
    status: str = Field(..., examples=["paid", "settlement", "success", "pending", "failed"])
    payment_method: str = Field(default="VA_BCA")
    paid_at: datetime | None = Field(default=None)


class WebhookSignPreviewRequest(BaseModel):
    transaction_id: str
    billing_id: int
    amount: int
    status: str = "paid"
    payment_method: str = "VA_BCA"


class KrsSubmitRequest(BaseModel):
    nim: str = Field(..., examples=["2401001"])
    semester: str = Field(..., examples=["2026/2027-Ganjil"])
    mata_kuliah: list[str] = Field(..., min_length=1, examples=[["Struktur Data", "Basis Data", "Pemrograman Web"]])
    total_sks: int = Field(..., gt=0, le=24, examples=[18])


class MahasiswaCreateRequest(BaseModel):
    nim: str = Field(..., min_length=4, max_length=20)
    nama: str = Field(..., min_length=2, max_length=120)
    email: str = Field(..., min_length=5, max_length=120)
    program_studi: str = Field(..., examples=["Teknik", "Ekonomi"])
    angkatan: int = Field(default=2024, ge=2015, le=2030)
    status_aktif: bool = Field(default=True)


class ApiMessage(BaseModel):
    message: str
    data: dict[str, Any] | None = None
