"""Algoritma deteksi bentrok jadwal 3 dimensi (waktu x ruangan x dosen).

Aturan inti:
- Setiap jadwal direpresentasikan sebagai interval setengah terbuka [jam_mulai, jam_selesai).
  Akibatnya kuliah bersambung (mis. 08:00-09:40 dan 09:40-11:20) TIDAK dianggap bentrok.
- Irisan waktu saja tanpa kesamaan ruangan atau dosen adalah kondisi normal (bukan konflik).
  Oleh karena itu tipe 'time_overlap' sengaja tidak digunakan; hanya 'room_conflict' dan
  'lecturer_conflict'.
- Versi naif O(n^2) dipertahankan sebagai pembanding (oracle) untuk differential testing
  terhadap versi teroptimasi grouping + sort & sweep O(n log n + k).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import time
from itertools import combinations
from typing import Any, Literal, Protocol

ConflictType = Literal["room_conflict", "lecturer_conflict"]


class ScheduleLike(Protocol):
    """Protokol atribut minimal yang dimiliki JadwalSlot maupun ORM Jadwal."""

    id: int
    hari: int
    jam_mulai: time
    jam_selesai: time
    ruangan_kode: str
    dosen_id: int


@dataclass(frozen=True)
class Conflict:
    """Representasi hasil deteksi konflik yang immutable (hashable untuk set/Counter)."""

    type: ConflictType
    affected: tuple[int, ...]  # id jadwal terlibat (terurut untuk pasangan)


@dataclass(frozen=True)
class JadwalSlot:
    """Representasi ringan jadwal tanpa ketergantungan database/ORM."""

    id: int
    hari: int
    jam_mulai: time
    jam_selesai: time
    ruangan_kode: str
    dosen_id: int


def overlap(a: ScheduleLike, b: ScheduleLike) -> bool:
    """Cek apakah dua jadwal bertumpuk pada hari sama dengan interval [mulai, selesai)."""
    return (
        a.hari == b.hari
        and a.jam_mulai < b.jam_selesai
        and b.jam_mulai < a.jam_selesai
    )


def _pasangan(tipe: ConflictType, a: ScheduleLike, b: ScheduleLike) -> Conflict:
    """Bentuk Conflict dengan urutan ID kanonik agar (A, B) == (B, A)."""
    return Conflict(tipe, tuple(sorted((a.id, b.id))))


def detect_naive(jadwal: Sequence[ScheduleLike]) -> list[Conflict]:
    """Detektor acuan O(n^2) memakai itertools.combinations agar tiap pasangan dicek sekali."""
    hasil: list[Conflict] = []
    for a, b in combinations(jadwal, 2):
        if not overlap(a, b):
            continue
        if a.ruangan_kode == b.ruangan_kode:
            hasil.append(_pasangan("room_conflict", a, b))
        if a.dosen_id == b.dosen_id:
            hasil.append(_pasangan("lecturer_conflict", a, b))
    return hasil


KUNCI: dict[ConflictType, Callable[[ScheduleLike], tuple[int, Any]]] = {
    "room_conflict": lambda j: (j.hari, j.ruangan_kode),
    "lecturer_conflict": lambda j: (j.hari, j.dosen_id),
}


def detect_schedule_conflict(jadwal: Sequence[ScheduleLike]) -> list[Conflict]:
    """Detektor teroptimasi O(n log n + k) dengan grouping + sort & sweep.

    1. Kelompokkan jadwal berdasarkan (hari, ruangan_kode) dan (hari, dosen_id).
    2. Urutkan setiap kelompok berdasarkan jam_mulai (sapu pagi -> sore).
    3. Pertahankan jadwal aktif yang belum selesai (x.jam_selesai > j.jam_mulai).
       Strict '>' menjaga kuliah bersambung tidak dianggap bentrok.
    4. Semua jadwal yang tersisa di daftar aktif pasti bertumpuk dengan jadwal baru.
    """
    hasil: list[Conflict] = []
    for tipe, kunci in KUNCI.items():
        grup: dict[tuple[int, Any], list[ScheduleLike]] = defaultdict(list)
        for j in jadwal:
            grup[kunci(j)].append(j)
        for anggota in grup.values():
            aktif: list[ScheduleLike] = []
            for j in sorted(anggota, key=lambda x: x.jam_mulai):
                aktif = [x for x in aktif if x.jam_selesai > j.jam_mulai]
                hasil.extend(_pasangan(tipe, x, j) for x in aktif)
                aktif.append(j)
    return hasil
