from app.models.akademik import Dosen, Jadwal, Kelas, KRS, KRSDetail, Mahasiswa, MataKuliah
from app.models.nilai import GradeHistory, SkalaNilai, VIEW_RIWAYAT_NILAI_SQL

__all__ = [
    "Mahasiswa",
    "Dosen",
    "MataKuliah",
    "Kelas",
    "Jadwal",
    "KRS",
    "KRSDetail",
    "SkalaNilai",
    "GradeHistory",
    "VIEW_RIWAYAT_NILAI_SQL",
]
