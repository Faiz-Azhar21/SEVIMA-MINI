"""Generator NIM otomatis yang aman dari race condition berbasis row-level locking DB."""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import NimCounter

KODE_PRODI_REGEX = re.compile(r"^\d{3}$")
MAX_RUNNING_NUMBER = 9999


def format_nim(tahun: int, kode_prodi: str, running_number: int) -> str:
    """Memformat komponen NIM menjadi 11 digit murni: [Tahun:4][Kode Prodi:3][Running:4].

    Contoh: format_nim(2025, "001", 7) -> "20250010007".
    """
    if not (1000 <= tahun <= 9999):
        raise ValueError("Tahun harus 4 digit (1000-9999)")
    if not KODE_PRODI_REGEX.fullmatch(kode_prodi):
        raise ValueError("Kode prodi harus tepat 3 digit angka")
    if not (1 <= running_number <= MAX_RUNNING_NUMBER):
        raise ValueError(f"Nomor urut NIM harus berada di rentang 1-{MAX_RUNNING_NUMBER}")
    return f"{tahun}{kode_prodi}{running_number:04d}"


def format_nim_display(nim: str) -> str:
    """Helper presentasi untuk menampilkan NIM 11 digit dengan tanda strip (2025001-0001)."""
    if not re.fullmatch(r"^\d{11}$", nim):
        raise ValueError("NIM harus tepat 11 digit angka")
    return f"{nim[:7]}-{nim[7:]}"


def generate_nim(tahun: int, kode_prodi: str, db: Session) -> str:
    """Menghasilkan NIM unik berurutan per (tahun, kode_prodi) dalam transaksi pemanggil.

    Desain concurrency:
    - Menggunakan tabel `nim_counter` dengan `SELECT ... FOR UPDATE` (row lock di MySQL InnoDB).
    - Baris baru diinisialisasi eksplisit dengan `last_number=0` sebelum increment.
    - Sengaja hanya memanggil `db.flush()` (BUKAN `db.commit()`) agar seluruh proses approve
      dan kenaikan counter berada dalam satu transaksi atomik milik pemanggil.
    """
    if not (1000 <= tahun <= 9999):
        raise ValueError("Tahun tidak valid (harus 4 digit)")
    if not KODE_PRODI_REGEX.fullmatch(kode_prodi):
        raise ValueError("Kode program studi tidak valid (harus 3 digit angka)")

    stmt = (
        select(NimCounter)
        .where(
            NimCounter.tahun == tahun,
            NimCounter.kode_prodi == kode_prodi,
        )
        .with_for_update()
    )
    counter = db.scalars(stmt).one_or_none()

    if counter is None:
        counter = NimCounter(tahun=tahun, kode_prodi=kode_prodi, last_number=0)
        db.add(counter)

    counter.last_number += 1
    if counter.last_number > MAX_RUNNING_NUMBER:
        raise ValueError("Nomor urut NIM sudah habis untuk tahun dan prodi ini")

    db.flush()
    return format_nim(tahun, kode_prodi, counter.last_number)
