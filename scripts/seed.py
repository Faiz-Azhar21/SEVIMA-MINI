"""Seed data untuk Modul Jadwal & Ruangan (Tugas Minggu 7).

Membuat:
- 12 ruangan (>= 10)
- 16 dosen (>= 15)
- 15 mata kuliah & 45 kelas paralel (semester 20251)
- 45 jadwal (>= 40): 42 jadwal normal (termasuk sesi bersambung 09:40) +
  3 jadwal bentrok sengaja (room_conflict, lecturer_conflict, dan double conflict)
  untuk mensimulasikan data hasil impor yang dideteksi oleh GET /api/jadwal/conflicts.
"""

from __future__ import annotations

import argparse
from datetime import time

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.database import Base, SessionLocal, engine
from app.models.jadwal import Dosen, Jadwal, Kelas, Ruangan
from app.models.krs import KRS, KRSDetail, MataKuliah
from app.services.conflict import detect_schedule_conflict

RUANGAN_DATA = [
    ("A101", "Ruang Kuliah A101", 40),
    ("A102", "Ruang Kuliah A102", 40),
    ("A103", "Ruang Kuliah A103", 50),
    ("A104", "Ruang Kuliah A104", 60),
    ("B201", "Ruang Kuliah B201", 45),
    ("B202", "Ruang Kuliah B202", 45),
    ("B203", "Ruang Kuliah B203", 50),
    ("B204", "Ruang Auditorium Mini B204", 80),
    ("LAB1", "Laboratorium Pemrograman 1", 30),
    ("LAB2", "Laboratorium Basis Data", 30),
    ("LAB3", "Laboratorium Jaringan", 35),
    ("LAB4", "Laboratorium AI & Data", 35),
]

DOSEN_DATA = [
    ("0010018001", "Dr. Daniel Wijaya, M.Kom."),
    ("0010018002", "Prof. Siti Rahmawati, Ph.D."),
    ("0010018003", "Budi Santoso, M.T."),
    ("0010018004", "Dr. Rina Kusuma, M.Cs."),
    ("0010018005", "Ahmad Fauzi, M.Kom."),
    ("0010018006", "Dewi Lestari, M.Sc."),
    ("0010018007", "Hendra Pratama, M.T."),
    ("0010018008", "Dr. Maya Sari, M.Kom."),
    ("0010018009", "Rizky Ramadhan, M.Cs."),
    ("0010018010", "Indah Permata, M.Kom."),
    ("0010018011", "Agus Setiawan, M.T."),
    ("0010018012", "Nadia Putri, M.Sc."),
    ("0010018013", "Fajar Nugroho, M.Kom."),
    ("0010018014", "Lina Marlina, M.T."),
    ("0010018015", "Eko Prasetyo, M.Cs."),
    ("0010018016", "Yuni Astuti, M.Kom."),
]

MATAKULIAH_DATA = [
    ("IF101", "Algoritma & Pemrograman", 3),
    ("IF102", "Matematika Diskrit", 3),
    ("IF103", "Kalkulus I", 3),
    ("IF201", "Struktur Data", 3),
    ("IF202", "Pemrograman Berorientasi Objek", 3),
    ("IF203", "Basis Data", 3),
    ("IF204", "Sistem Operasi", 3),
    ("IF205", "Jaringan Komputer", 3),
    ("IF301", "Rekayasa Perangkat Lunak", 3),
    ("IF302", "Statistika & Probabilitas", 3),
    ("IF303", "Kecerdasan Buatan", 3),
    ("IF304", "Pemrograman Web", 3),
    ("IF305", "Interaksi Manusia & Komputer", 2),
    ("IF306", "Keamanan Informasi", 3),
    ("IF307", "Analisis Algoritma", 3),
]

# Slot blok 50 menit x 2 SKS (100 menit) yang bersambung rapi (interval setengah terbuka)
SLOTS = [
    (time(8, 0), time(9, 40)),
    (time(9, 40), time(11, 20)),
    (time(11, 20), time(13, 0)),
    (time(13, 30), time(15, 10)),
    (time(15, 10), time(16, 50)),
]


def seed_database(db: Session, reset: bool = False) -> dict[str, int]:
    """Isi database dengan data contoh terstruktur dan deterministik."""
    if reset:
        db.execute(delete(KRSDetail))
        db.execute(delete(KRS))
        db.execute(delete(Jadwal))
        db.execute(delete(Kelas))
        db.execute(delete(MataKuliah))
        db.execute(delete(Dosen))
        db.execute(delete(Ruangan))
        db.commit()

    existing_jadwal = db.scalar(select(func.count()).select_from(Jadwal)) or 0
    if existing_jadwal > 0:
        konflik = detect_schedule_conflict(list(db.scalars(select(Jadwal)).all()))
        return {
            "ruangan": db.scalar(select(func.count()).select_from(Ruangan)) or 0,
            "dosen": db.scalar(select(func.count()).select_from(Dosen)) or 0,
            "kelas": db.scalar(select(func.count()).select_from(Kelas)) or 0,
            "jadwal": existing_jadwal,
            "konflik": len(konflik),
        }

    # 1. Ruangan (12)
    for kode, nama, kapasitas in RUANGAN_DATA:
        db.add(Ruangan(kode=kode, nama=nama, kapasitas=kapasitas))

    # 2. Dosen (16)
    dosen_list: list[Dosen] = []
    for nidn, nama in DOSEN_DATA:
        d = Dosen(nidn=nidn, nama=nama)
        db.add(d)
        dosen_list.append(d)

    # 3. Mata Kuliah (15)
    for kode_mk, nama, sks in MATAKULIAH_DATA:
        db.add(MataKuliah(kode_mk=kode_mk, nama=nama, sks=sks))

    db.flush()

    # 4. Kelas Paralel (45 kelas: A, B, C untuk 15 MK)
    kelas_list: list[Kelas] = []
    for idx, (kode_mk, _nama, _sks) in enumerate(MATAKULIAH_DATA):
        for suffix in ("A", "B", "C"):
            kuota = 30 if suffix == "C" else 35
            k = Kelas(
                kode_mk=kode_mk,
                nama_kelas=f"{kode_mk}-{suffix}",
                kuota=kuota,
                semester="20251",
            )
            db.add(k)
            kelas_list.append(k)

    db.flush()

    # 5. 42 Jadwal normal bebas bentrok (tersebar Senin-Sabtu, 7 jadwal/hari)
    #    Setiap hari memakai 7 slot berbeda atau kombinasi (ruang, dosen) yang dijamin unik
    ruang_kodes = [r[0] for r in RUANGAN_DATA]  # 12 ruangan
    normal_jadwal: list[Jadwal] = []
    jadwal_idx = 0
    for hari in range(1, 7):  # Senin (1) .. Sabtu (6)
        # 7 jadwal per hari -> total 42 jadwal normal
        # Pakai 2 ruang berbeda pada slot 0 & 1 (termasuk sesi bersambung 09:40 di A101!)
        konfigurasi_harian = [
            # (slot_idx, ruang_idx, dosen_idx)
            (0, 0, (hari - 1) % 16),          # A101, 08:00-09:40
            (1, 0, (hari + 1) % 16),          # A101, 09:40-11:20 (bersambung, TIDAK bentrok!)
            (0, 1, (hari + 2) % 16),          # A102, 08:00-09:40 (waktu sama, ruang & dosen beda -> normal)
            (1, 4, (hari + 4) % 16),          # B201, 09:40-11:20
            (2, 2, (hari + 6) % 16),          # A103, 11:20-13:00
            (3, 8, (hari + 8) % 16),          # LAB1, 13:30-15:10
            (4, 9, (hari + 10) % 16),         # LAB2, 15:10-16:50
        ]
        for slot_idx, ruang_idx, dosen_idx in konfigurasi_harian:
            mulai, selesai = SLOTS[slot_idx]
            j = Jadwal(
                kelas_id=kelas_list[jadwal_idx].id,
                hari=hari,
                jam_mulai=mulai,
                jam_selesai=selesai,
                ruangan_kode=ruang_kodes[ruang_idx],
                dosen_id=dosen_list[dosen_idx].id,
            )
            db.add(j)
            normal_jadwal.append(j)
            jadwal_idx += 1

    # 6. 3 Jadwal bentrok sengaja (disisipkan langsung, bypass SchedulingService)
    #    Simulasi data legacy/impor agar GET /api/jadwal/conflicts melaporkannya:
    #
    #    (a) Bentrok ruangan SAJA di A101 Senin 08:30-10:00 (tabrakan dgn slot 0 & slot 1 A101 Senin)
    db.add(
        Jadwal(
            kelas_id=kelas_list[42].id,
            hari=1,
            jam_mulai=time(8, 30),
            jam_selesai=time(9, 30),
            ruangan_kode="A101",
            dosen_id=dosen_list[15].id,  # dosen 16 bebas di Senin 08:30
        )
    )
    #    (b) Bentrok dosen SAJA di Selasa 08:30-09:30 (dosen_list[1] sedang mengajar A101 Selasa 08:00-09:40)
    db.add(
        Jadwal(
            kelas_id=kelas_list[43].id,
            hari=2,
            jam_mulai=time(8, 30),
            jam_selesai=time(9, 30),
            ruangan_kode="A104",  # ruang kosong
            dosen_id=dosen_list[1].id,  # sama dengan jadwal #1 hari Selasa
        )
    )
    #    (c) Bentrok GANDA (ruangan + dosen sekaligus) di B201 Rabu 10:00-11:00
    #        (bertabrakan dgn jadwal B201 Rabu 09:40-11:20 milik dosen_list[(3+4)%16 = 7])
    db.add(
        Jadwal(
            kelas_id=kelas_list[44].id,
            hari=3,
            jam_mulai=time(10, 0),
            jam_selesai=time(11, 0),
            ruangan_kode="B201",
            dosen_id=dosen_list[7].id,
        )
    )

    # 7. Beberapa sample KRS + KRSDetail untuk memverifikasi query hitung peserta terdaftar
    for mhs_idx in range(1, 6):
        krs = KRS(nim=f"230100{mhs_idx:02d}", semester="20251", status="APPROVED")
        db.add(krs)
        db.flush()
        db.add(
            KRSDetail(
                krs_id=krs.id,
                kode_mk=kelas_list[0].kode_mk,
                kelas_id=kelas_list[0].id,
            )
        )

    db.commit()

    semua = list(db.scalars(select(Jadwal)).all())
    konflik = detect_schedule_conflict(semua)
    return {
        "ruangan": len(RUANGAN_DATA),
        "dosen": len(DOSEN_DATA),
        "kelas": len(kelas_list),
        "jadwal": len(semua),
        "konflik": len(konflik),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed database SEVIMA-Mini Minggu 7.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Hapus data lama sebelum mengisi ulang seed data.",
    )
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        ringkasan = seed_database(db, reset=args.reset)
    print(
        f"Seed selesai: {ringkasan['ruangan']} ruangan, {ringkasan['dosen']} dosen, "
        f"{ringkasan['kelas']} kelas, {ringkasan['jadwal']} jadwal, "
        f"{ringkasan['konflik']} konflik terdeteksi."
    )


if __name__ == "__main__":
    main()
