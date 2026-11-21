"""Port & Stub Presensi (Dependency Inversion Principle).

Modul Presensi sesungguhnya baru dibangun di Minggu 12.
GradeService hanya bergantung pada PresensiPort sehingga implementasi
dapat diganti di Minggu 12 tanpa mengubah kode GradeService.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

MIN_PRESENSI = Decimal("75")


class PresensiPort(Protocol):  # implementasi asli: Minggu 12
    def persentase(self, nim: str, kelas_id: int) -> Decimal: ...


class PresensiStub:  # implementasi sementara Minggu 9
    def __init__(
        self,
        data: dict[tuple[str, int], Decimal] | None = None,
        default: Decimal = Decimal("100"),
    ) -> None:
        self.data = data if data is not None else {}
        self.default = default

    def persentase(self, nim: str, kelas_id: int) -> Decimal:
        return self.data.get((nim, kelas_id), self.default)
