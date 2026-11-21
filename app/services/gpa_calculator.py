"""GPACalculator — mengorkestrasi NilaiRepo dan fungsi murni domain GPA."""

from __future__ import annotations

from decimal import Decimal

from app.domain.gpa import hitung_ipk, hitung_ips
from app.repositories.nilai_repo import NilaiRepo


class GPACalculator:
    """Menyediakan antarmuka calculate_ips dan calculate_ipk sesuai spesifikasi tugas."""

    def __init__(self, repo: NilaiRepo) -> None:
        self.repo = repo

    def calculate_ips(self, nim: str, semester: str) -> Decimal:
        """Hitung IPS mahasiswa untuk semester tertentu (compute-on-read)."""
        return hitung_ips(self.repo.records(nim), semester, self.repo.skala())

    def calculate_ipk(self, nim: str) -> Decimal:
        """Hitung IPK kumulatif mahasiswa (compute-on-read)."""
        return hitung_ipk(self.repo.records(nim), self.repo.skala())
