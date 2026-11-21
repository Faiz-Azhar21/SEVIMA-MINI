"""Domain murni untuk perhitungan IPS & IPK tanpa ketergantungan database.

Aturan kerja:
- Memakai Decimal (BUKAN float) dengan pembulatan ROUND_HALF_UP dua desimal sekali di akhir.
- IPS menghitung seluruh MK pada semester target, termasuk E.
- IPK memilih nilai terbaik (berdasarkan bobot tertinggi) per kode_mk terlebih dahulu,
  lalu menyaring hanya MK yang status lulusnya True pada tabel skala_nilai.
- Mahasiswa baru / belum memiliki nilai lulus mengembalikan Decimal("0.00").
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

DUA_DESIMAL = Decimal("0.01")


@dataclass(frozen=True)
class Skala:
    """Representasi bobot angka (Decimal) dan status kelulusan untuk satu huruf nilai."""

    bobot: Decimal
    lulus: bool


@dataclass(frozen=True)
class NilaiRecord:
    """Bentuk data paling sederhana yang dibutuhkan perhitungan IPS dan IPK."""

    kode_mk: str
    semester: str  # contoh: "20241"
    sks: int
    huruf: str


def _rata(records: Sequence[NilaiRecord], skala: Mapping[str, Skala]) -> Decimal:
    total_sks = sum(r.sks for r in records)
    if total_sks == 0:
        return Decimal("0.00")  # mahasiswa baru / belum ada nilai
    mutu = sum((skala[r.huruf].bobot * r.sks for r in records), Decimal("0"))
    return (mutu / Decimal(total_sks)).quantize(DUA_DESIMAL, rounding=ROUND_HALF_UP)


def hitung_ips(
    records: Sequence[NilaiRecord],
    semester: str,
    skala: Mapping[str, Skala],
) -> Decimal:
    """Hitung Indeks Prestasi Semester (IPS) — semua MK di semester tersebut termasuk E."""
    return _rata([r for r in records if r.semester == semester], skala)


def hitung_ipk(
    records: Sequence[NilaiRecord],
    skala: Mapping[str, Skala],
) -> Decimal:
    """Hitung Indeks Prestasi Kumulatif (IPK).

    Urutan:
    1. Deduplikasi per kode_mk dengan memilih bobot tertinggi (bukan max pada string huruf).
    2. Saring hanya MK yang lulus berdasarkan skala[huruf].lulus.
    3. Hitung Σ(bobot × SKS) / Σ(SKS) dan bulatkan ROUND_HALF_UP sekali di akhir.
    """
    terbaik: dict[str, NilaiRecord] = {}
    for r in records:  # per kode_mk
        lama = terbaik.get(r.kode_mk)
        if lama is None or skala[r.huruf].bobot > skala[lama.huruf].bobot:
            terbaik[r.kode_mk] = r  # bandingkan bobot, bukan huruf
    lulus = [r for r in terbaik.values() if skala[r.huruf].lulus]
    return _rata(lulus, skala)
