"""Ekspos seluruh model ORM agar otomatis terdaftar di Base.metadata."""

from app.models.base import Base
from app.models.krs import KRS, KRSDetail, KRSStatus, MataKuliah, SkalaNilai, prerequisite
from app.models.pmb import CalonMahasiswa, PMBStatus

__all__ = [
    "Base",
    "CalonMahasiswa",
    "PMBStatus",
    "KRS",
    "KRSDetail",
    "KRSStatus",
    "MataKuliah",
    "SkalaNilai",
    "prerequisite",
]
