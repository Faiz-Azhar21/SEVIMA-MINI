"""Implementasi 4 validator aturan bisnis KRS (Step 1).

Urutan rantai default yang disarankan (tercatat pada ADR-001):
Duplicate -> SKS -> Prerequisite -> Conflict
"""

from __future__ import annotations

from app.models.krs import MataKuliah
from app.queries.prerequisite import prasyarat_belum_lulus
from app.validators.base import KRSContext, ValidationResult, Validator

MAX_SKS = 24  # Single source of truth untuk batas SKS maksimal per semester


class DuplicateValidator(Validator):
    """Aturan 3: Tidak boleh mengambil mata kuliah yang sama dua kali dalam satu KRS."""

    def check(self, ctx: KRSContext) -> ValidationResult:
        if any(d.kode_mk == ctx.mk_baru.kode_mk for d in ctx.details):
            return ValidationResult(False, f"Sudah ada di KRS: {ctx.mk_baru.nama}")
        return ValidationResult(True)


class SKSValidator(Validator):
    """Aturan 1: Total SKS per semester tidak boleh melebihi MAX_SKS (24)."""

    def __init__(self, max_sks: int = MAX_SKS) -> None:
        self.max_sks = max_sks

    def check(self, ctx: KRSContext) -> ValidationResult:
        total = sum(d.matakuliah.sks for d in ctx.details) + ctx.mk_baru.sks
        if total > self.max_sks:
            return ValidationResult(
                False,
                f"Total SKS {total} melebihi batas {self.max_sks}",
            )
        return ValidationResult(True)


class PrerequisiteValidator(Validator):
    """Aturan 2: Semua prasyarat mata kuliah harus lulus (>= C) di semester sebelumnya."""

    def check(self, ctx: KRSContext) -> ValidationResult:
        kurang = prasyarat_belum_lulus(
            ctx.db,
            ctx.nim,
            ctx.mk_baru.kode_mk,
            ctx.semester,
        )
        if kurang:
            return ValidationResult(
                False,
                "Prasyarat tidak terpenuhi: " + ", ".join(kurang),
            )
        return ValidationResult(True)


def bentrok(a: MataKuliah, b: MataKuliah) -> bool:
    """Deteksi bentrok jadwal dengan rumus irisan interval.

    Menggunakan `<` (bukan `<=`), sehingga kuliah bersambung
    (mis. selesai 10:30, kelas berikutnya mulai 10:30) diperbolehkan.
    """
    return (
        a.hari == b.hari
        and a.jam_mulai < b.jam_selesai
        and b.jam_mulai < a.jam_selesai
    )


class ConflictValidator(Validator):
    """Aturan 4: Jadwal mata kuliah baru tidak boleh bertumpuk dengan MK lain di KRS."""

    def check(self, ctx: KRSContext) -> ValidationResult:
        for d in ctx.details:
            if bentrok(d.matakuliah, ctx.mk_baru):
                return ValidationResult(
                    False,
                    f"Jadwal bentrok: {ctx.mk_baru.nama} dengan {d.matakuliah.nama}",
                )
        return ValidationResult(True)


def default_validators() -> list[Validator]:
    """Kembalikan daftar validator bawaan dalam urutan optimal (lihat ADR-001)."""
    return [
        DuplicateValidator(),
        SKSValidator(),
        PrerequisiteValidator(),
        ConflictValidator(),
    ]
