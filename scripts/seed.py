"""Script seeding data dummy SEVIMA-Mini (Modul PMB + Modul KRS).

Menggunakan data dummy sepenuhnya (sesuai AI-First Charter, tanpa data asli).
Bersifat idempotent: aman dijalankan berulang kali.
"""

from __future__ import annotations

import sys
from datetime import time
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

# Pastikan root proyek ada di sys.path saat dijalankan langsung
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.database import SessionLocal
from app.models import (
    KRS,
    KRSDetail,
    KRSStatus,
    MataKuliah,
    PMBStatus,
    SkalaNilai,
    CalonMahasiswa,
)


def seed_database(db: Session) -> None:
    """Isi data dummy awal untuk skala_nilai, calon_mahasiswa, matakuliah, prasyarat, dan histori KRS."""
    # 1. Skala Nilai (A=4 .. E=0)
    skala_data = [
        ("A", 4.00),
        ("B", 3.00),
        ("C", 2.00),
        ("D", 1.00),
        ("E", 0.00),
    ]
    for huruf, bobot in skala_data:
        if db.get(SkalaNilai, huruf) is None:
            db.add(SkalaNilai(huruf=huruf, bobot=bobot))
    db.flush()

    # 2. Calon Mahasiswa (dummy dari Modul PMB)
    mahasiswa_data = [
        {
            "nama": "Budi Santoso",
            "email": "budi.dummy@kampus.example",
            "prodi": "Informatika",
            "status": PMBStatus.APPROVED,
            "nim": "202401001",
        },
        {
            "nama": "Ani Wijaya",
            "email": "ani.dummy@kampus.example",
            "prodi": "Informatika",
            "status": PMBStatus.APPROVED,
            "nim": "202401002",
        },
        {
            "nama": "Citra Lestari",
            "email": "citra.dummy@kampus.example",
            "prodi": "Informatika",
            "status": PMBStatus.APPROVED,
            "nim": "202401003",
        },
        {
            "nama": "Dodi Pendaftar",
            "email": "dodi.dummy@kampus.example",
            "prodi": "Informatika",
            "status": PMBStatus.PENDING,
            "nim": None,
        },
    ]
    for m in mahasiswa_data:
        existing = db.scalar(select(CalonMahasiswa).where(CalonMahasiswa.email == m["email"]))
        if existing is None:
            db.add(CalonMahasiswa(**m))
    db.flush()

    # 3. Mata Kuliah (berbagai SKS & jadwal termasuk kasus bentrok & bersambung)
    mk_data = [
        ("MA101", "Kalkulus I", 3, 1, time(8, 0), time(10, 30)),
        ("MA201", "Kalkulus II", 3, 2, time(8, 0), time(10, 30)),
        ("IF101", "Algoritma & Pemrograman", 4, 1, time(10, 30), time(13, 0)),  # bersambung dgn MA101
        ("IF201", "Struktur Data", 4, 3, time(8, 0), time(10, 30)),
        ("IF202", "Basis Data", 3, 1, time(8, 0), time(10, 30)),
        ("IF203", "Statistika", 3, 1, time(9, 0), time(11, 0)),  # bentrok sebagian dgn IF202
        ("IF204", "Jaringan Komputer", 3, 4, time(8, 0), time(10, 30)),
        ("IF205", "Sistem Operasi", 4, 5, time(8, 0), time(11, 0)),
        ("IF206", "Pemrograman Berorientasi Objek", 4, 2, time(13, 0), time(16, 0)),
        ("IF207", "Kecerdasan Buatan", 4, 3, time(13, 0), time(16, 0)),
        ("IF208", "Etika Profesi", 2, 4, time(13, 0), time(15, 0)),
        ("IF209", "Kewirausahaan", 2, 5, time(13, 0), time(15, 0)),
        ("IF210", "Rekayasa Perangkat Lunak", 4, 6, time(8, 0), time(11, 0)),
    ]
    mk_map: dict[str, MataKuliah] = {}
    for kode, nama, sks, hari, mulai, selesai in mk_data:
        mk = db.get(MataKuliah, kode)
        if mk is None:
            mk = MataKuliah(
                kode_mk=kode,
                nama=nama,
                sks=sks,
                hari=hari,
                jam_mulai=mulai,
                jam_selesai=selesai,
            )
            db.add(mk)
        mk_map[kode] = mk
    db.flush()

    # 4. Prasyarat (self-referencing many-to-many)
    prasyarat_edges = [
        ("MA201", "MA101"),  # Kalkulus II butuh Kalkulus I
        ("IF201", "IF101"),  # Struktur Data butuh Algoritma & Pemrograman
        ("IF202", "IF201"),  # Basis Data butuh Struktur Data
        ("IF206", "IF101"),  # PBO butuh Algoritma & Pemrograman
        ("IF207", "IF201"),  # AI butuh Struktur Data
        ("IF207", "MA101"),  # AI juga butuh Kalkulus I (multi-prasyarat)
    ]
    for kode_mk, kode_pra in prasyarat_edges:
        mk = mk_map[kode_mk]
        pra = mk_map[kode_pra]
        if pra not in mk.prasyarat:
            mk.prasyarat.append(pra)
    db.flush()

    # 5. Riwayat KRS Semester Sebelumnya (20242) untuk pengujian prasyarat
    def _ensure_krs(nim: str, semester: str, status: KRSStatus, items: list[tuple[str, str | None]]) -> None:
        krs = db.scalar(select(KRS).where(KRS.nim == nim, KRS.semester == semester))
        if krs is None:
            krs = KRS(nim=nim, semester=semester, status=status)
            db.add(krs)
            db.flush()
            for kode_mk, nilai in items:
                db.add(KRSDetail(krs_id=krs.id, kode_mk=kode_mk, nilai=nilai))

    # Budi: lulus IF101 (B), tidak lulus MA101 (D)
    _ensure_krs(
        nim="202401001",
        semester="20242",
        status=KRSStatus.APPROVED,
        items=[("IF101", "B"), ("MA101", "D")],
    )

    # Ani: lulus IF101 (A), lulus tepat batas MA101 (C), lulus IF201 (B)
    _ensure_krs(
        nim="202401002",
        semester="20242",
        status=KRSStatus.APPROVED,
        items=[("IF101", "A"), ("MA101", "C"), ("IF201", "B")],
    )

    # Citra: sudah punya KRS semester aktif 20251 berstatus SUBMITTED (tidak bisa diubah)
    _ensure_krs(
        nim="202401003",
        semester="20251",
        status=KRSStatus.SUBMITTED,
        items=[("MA101", None)],
    )

    db.commit()


def main() -> None:
    with SessionLocal() as db:
        seed_database(db)
    print("Seeding data dummy SEVIMA-Mini selesai.")


if __name__ == "__main__":
    main()
