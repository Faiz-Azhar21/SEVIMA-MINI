"""Definisi tabel transisi State Machine KRS.

Aturan ketat:
- Hanya pasangan (status_asal, aktor) yang terdaftar yang diizinkan berpindah.
- Pasangan yang tidak tercantum otomatis mengembalikan himpunan kosong (ditolak).
- Tidak ada jalur langsung DRAFT -> APPROVED atau REVISION -> APPROVED.
- APPROVED adalah status akhir (terminal).
"""

from app.enums import Actor, KRSStatus

TRANSITIONS: dict[tuple[KRSStatus, Actor], set[KRSStatus]] = {
    (KRSStatus.DRAFT, Actor.MAHASISWA): {KRSStatus.SUBMITTED},
    (KRSStatus.SUBMITTED, Actor.DOSEN_PA): {KRSStatus.APPROVED, KRSStatus.REVISION},
    (KRSStatus.REVISION, Actor.MAHASISWA): {KRSStatus.SUBMITTED},
}

EDITABLE_STATUSES: frozenset[KRSStatus] = frozenset(
    {KRSStatus.DRAFT, KRSStatus.REVISION}
)
