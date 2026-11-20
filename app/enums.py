"""Enumerasi domain Modul KRS."""

import enum


class KRSStatus(str, enum.Enum):
    """Status siklus hidup KRS (State Machine)."""

    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    REVISION = "REVISION"


class Actor(str, enum.Enum):
    """Aktor yang dapat memicu transisi state pada KRS."""

    MAHASISWA = "MAHASISWA"
    DOSEN_PA = "DOSEN_PA"


class JenisMK(str, enum.Enum):
    """Kategori mata kuliah untuk prioritas rekomendasi KRS."""

    WAJIB = "WAJIB"
    PILIHAN = "PILIHAN"


NILAI_BOBOT: dict[str, float] = {
    "A": 4.0,
    "A-": 3.7,
    "B+": 3.3,
    "B": 3.0,
    "B-": 2.7,
    "C+": 2.3,
    "C": 2.0,
    "D": 1.0,
    "E": 0.0,
}

HARI_NAMA: dict[int, str] = {
    1: "Senin",
    2: "Selasa",
    3: "Rabu",
    4: "Kamis",
    5: "Jumat",
    6: "Sabtu",
}
