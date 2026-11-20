"""Abstract base class dan utilitas Chain of Responsibility untuk validasi KRS."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.krs import KRSDetail, MataKuliah


@dataclass(frozen=True)
class ValidationResult:
    """Hasil validasi immutable: status lolos (`ok`) dan pesan spesifik (`message`)."""

    ok: bool
    message: str = ""


@dataclass
class KRSContext:
    """Wadah data seragam yang diterima oleh seluruh validator dalam rantai."""

    nim: str
    semester: str
    details: list[KRSDetail]  # MK lain yang sudah ada di KRS
    mk_baru: MataKuliah
    db: Session


class Validator(ABC):
    """Abstract base class Chain of Responsibility + Template Method.

    Logika merantai ditulis sekali di `validate()`; setiap turunan hanya perlu
    mengimplementasikan satu aturan bisnis pada `check()`.
    """

    _next: Validator | None = None

    def set_next(self, nxt: Validator) -> Validator:
        """Pasang validator berikutnya dan kembalikan agar bisa dirantai (fluent)."""
        self._next = nxt
        return nxt

    def validate(self, ctx: KRSContext) -> ValidationResult:
        """Jalankan pemeriksaan sendiri; berhenti di kegagalan pertama (fail-fast)."""
        hasil = self.check(ctx)
        if not hasil.ok or self._next is None:
            return hasil
        return self._next.validate(ctx)

    @abstractmethod
    def check(self, ctx: KRSContext) -> ValidationResult:
        """Periksa satu aturan bisnis terhadap konteks KRS."""


def build_chain(vs: list[Validator]) -> Validator:
    """Rangkai daftar validator secara berurutan dan kembalikan kepala rantai."""
    if not vs:
        raise ValueError("Daftar validator tidak boleh kosong")
    for a, b in zip(vs, vs[1:]):
        a.set_next(b)
    vs[-1]._next = None
    return vs[0]
