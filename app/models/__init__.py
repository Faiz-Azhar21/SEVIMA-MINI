"""Ekspor seluruh model ORM agar terdaftar di Base.metadata (termasuk untuk Alembic)."""

from app.models.jadwal import Dosen, Jadwal, Kelas, Ruangan
from app.models.krs import KRS, KRSDetail, MataKuliah

__all__ = [
    "MataKuliah",
    "KRS",
    "KRSDetail",
    "Ruangan",
    "Dosen",
    "Kelas",
    "Jadwal",
]
