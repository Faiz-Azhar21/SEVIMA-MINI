"""Validasi aturan bisnis KRS dengan pola Chain of Responsibility (Step 1).

Validator berurutan:
1. SKSValidator          : cek total SKS <= 24
2. PrerequisiteValidator : cek nilai MK prasyarat >= C di semester sebelumnya
3. ConflictValidator     : cek bentrok jadwal (hari sama + jam overlap)
4. DuplicateValidator    : cek double enrollment (kode MK / MK induk sama)

Setiap validator mengembalikan `ValidationResult(ok, message)`.
Rantai (`handle`) berhenti langsung pada kegagalan pertama.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from app.enums import HARI_NAMA
from app.models import KRSDetail, Matakuliah
from app.queries import get_unmet_prerequisites

MAX_SKS_PER_SEMESTER = 24


@dataclass(frozen=True)
class ValidationResult:
    """Hasil eksekusi satu atau rantai validator."""

    ok: bool
    message: str = ""

    @property
    def passed(self) -> bool:
        """Alias boolean untuk kompatibilitas istilah pass/fail."""
        return self.ok

    @classmethod
    def success(cls) -> "ValidationResult":
        return cls(ok=True, message="")

    @classmethod
    def fail(cls, message: str) -> "ValidationResult":
        return cls(ok=False, message=message)


@dataclass
class KRSContext:
    """Konteks data yang dilewatkan sepanjang rantai validator."""

    nim: str
    details: list[KRSDetail]
    mk: Matakuliah
    db: Optional[Session] = None
    semester: int = 2


def is_schedule_conflict(mk_a: Matakuliah, mk_b: Matakuliah) -> bool:
    """Mengembalikan True jika dua mata kuliah berada di hari yang sama
    dan rentang jamnya saling tumpang tindih.

    Jadwal bersebelahan persis (mis. 08:00-10:00 dan 10:00-12:00) tidak bentrok.
    """
    if mk_a.hari != mk_b.hari:
        return False
    return mk_a.jam_mulai < mk_b.jam_selesai and mk_b.jam_mulai < mk_a.jam_selesai


class Validator(ABC):
    """Abstract base class untuk Chain of Responsibility pattern."""

    def __init__(self) -> None:
        self._next: Optional["Validator"] = None

    def set_next(self, validator: "Validator") -> "Validator":
        """Menghubungkan validator berikutnya dan mengembalikannya untuk chaining."""
        self._next = validator
        return validator

    @abstractmethod
    def validate(self, ctx: KRSContext) -> ValidationResult:
        """Mengevaluasi satu aturan bisnis pada konteks KRS."""

    def handle(self, ctx: KRSContext) -> ValidationResult:
        """Menjalankan rantai validasi; berhenti pada kegagalan pertama."""
        result = self.validate(ctx)
        if not result.ok:
            return result
        if self._next is not None:
            return self._next.handle(ctx)
        return ValidationResult.success()


class SKSValidator(Validator):
    """Validator 1: memastikan total SKS per semester tidak melebihi 24."""

    def __init__(self, max_sks: int = MAX_SKS_PER_SEMESTER) -> None:
        super().__init__()
        self.max_sks = max_sks

    def validate(self, ctx: KRSContext) -> ValidationResult:
        total_saat_ini = sum(
            d.matakuliah.sks for d in ctx.details if d.matakuliah is not None
        )
        proyeksi_total = total_saat_ini + ctx.mk.sks
        if proyeksi_total > self.max_sks:
            return ValidationResult.fail(
                f"Total SKS melebihi batas maksimal {self.max_sks} SKS "
                f"(saat ini {total_saat_ini} SKS + {ctx.mk.sks} SKS = {proyeksi_total} SKS)"
            )
        return ValidationResult.success()


class PrerequisiteValidator(Validator):
    """Validator 2: memastikan seluruh prasyarat MK sudah lulus (nilai >= C)
    pada semester sebelumnya."""

    def validate(self, ctx: KRSContext) -> ValidationResult:
        if ctx.db is None:
            return ValidationResult.success()

        unmet = get_unmet_prerequisites(
            db=ctx.db,
            nim=ctx.nim,
            kode_mk=ctx.mk.kode_mk,
            semester_sekarang=ctx.semester,
        )
        if unmet:
            daftar_nama = ", ".join(item.nama for item in unmet)
            return ValidationResult.fail(f"Prasyarat tidak terpenuhi: {daftar_nama}")
        return ValidationResult.success()


class ConflictValidator(Validator):
    """Validator 3: memastikan jadwal MK baru tidak bentrok dengan MK di KRS."""

    def validate(self, ctx: KRSContext) -> ValidationResult:
        for detail in ctx.details:
            existing = detail.matakuliah
            if existing is None or existing.kode_mk == ctx.mk.kode_mk:
                # Duplicate exact kode_mk ditangani oleh DuplicateValidator
                continue
            if is_schedule_conflict(existing, ctx.mk):
                hari_str = HARI_NAMA.get(existing.hari, f"Hari {existing.hari}")
                jam_str = (
                    f"{existing.jam_mulai.strftime('%H:%M')}-"
                    f"{existing.jam_selesai.strftime('%H:%M')}"
                )
                return ValidationResult.fail(
                    f"Jadwal bentrok dengan {existing.nama} ({hari_str} {jam_str})"
                )
        return ValidationResult.success()


class DuplicateValidator(Validator):
    """Validator 4: mencegah double enrollment (MK yang sama atau kelas paralel lain)."""

    def validate(self, ctx: KRSContext) -> ValidationResult:
        for detail in ctx.details:
            existing = detail.matakuliah
            if existing is None:
                continue
            if existing.kode_mk == ctx.mk.kode_mk:
                return ValidationResult.fail(
                    f"Mata kuliah sudah diambil (double enrollment): "
                    f"{ctx.mk.nama} ({ctx.mk.kode_mk})"
                )
            if existing.effective_kode_induk == ctx.mk.effective_kode_induk:
                return ValidationResult.fail(
                    f"Double enrollment: {ctx.mk.nama} sudah diambil di kelas lain "
                    f"({existing.kode_mk})"
                )
        return ValidationResult.success()


def build_validation_chain(max_sks: int = MAX_SKS_PER_SEMESTER) -> Validator:
    """Merakit Chain of Responsibility sesuai urutan Step 1 dokumen tugas:
    SKSValidator -> PrerequisiteValidator -> ConflictValidator -> DuplicateValidator.
    """
    sks = SKSValidator(max_sks=max_sks)
    prereq = PrerequisiteValidator()
    conflict = ConflictValidator()
    duplicate = DuplicateValidator()

    sks.set_next(prereq).set_next(conflict).set_next(duplicate)
    return sks
