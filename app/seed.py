"""Data awal (seed) SEVIMA-Mini untuk demo Conflict Resolver, Observer, KRS, & .ics."""

from __future__ import annotations

from datetime import time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.krs.models import KRS, KRSDetail, KRSStatus, Mahasiswa
from app.scheduling.models import Dosen, Jadwal, Kelas, Ruangan


def seed_demo_data(db: Session) -> dict[str, int]:
    """Mengisi data awal jika tabel ruangan masih kosong.

    Menyertakan 2 pasangan jadwal bentrok (room_conflict dan lecturer_conflict)
    agar Dashboard Conflict Resolver langsung dapat didemonstrasikan.
    """
    existing = db.scalar(select(func.count(Ruangan.kode))) or 0
    if existing > 0:
        return {"seeded": 0}

    ruangan = [
        Ruangan(kode="A101", nama="Ruang Kuliah A101", kapasitas=40),
        Ruangan(kode="A102", nama="Ruang Kuliah A102", kapasitas=40),
        Ruangan(kode="B201", nama="Ruang Kuliah B201", kapasitas=45),
        Ruangan(kode="C301", nama="Auditorium Mini C301", kapasitas=60),
        Ruangan(kode="LAB1", nama="Lab Kecil 1", kapasitas=25),
    ]
    db.add_all(ruangan)

    dosen = [
        Dosen(id=1, nidn="0011018501", nama="Dr. Budi Santoso", email="budi@sevima-mini.ac.id"),
        Dosen(id=2, nidn="0022038702", nama="Dr. Sari Wulandari", email="sari@sevima-mini.ac.id"),
        Dosen(id=3, nidn="0015077903", nama="Prof. Ahmad Fauzi", email="ahmad@sevima-mini.ac.id"),
    ]
    db.add_all(dosen)

    kelas = [
        Kelas(id=1, kode_mk="IF201", nama="Pemrograman Berorientasi Objek", kuota=40),
        Kelas(id=2, kode_mk="IF202", nama="Basis Data", kuota=35),
        Kelas(id=3, kode_mk="MA101", nama="Kalkulus I", kuota=40),
        Kelas(id=4, kode_mk="MA201", nama="Statistika", kuota=35),
        Kelas(id=5, kode_mk="IF305", nama="Kecerdasan Buatan", kuota=30),
    ]
    db.add_all(kelas)

    mahasiswa = [
        Mahasiswa(nim="2301001", nama="Rina Kusuma", email="rina@mhs.sevima-mini.ac.id"),
        Mahasiswa(nim="2301002", nama="Doni Pratama", email="doni@mhs.sevima-mini.ac.id"),
        Mahasiswa(nim="2301003", nama="Siti Aminah", email="siti@mhs.sevima-mini.ac.id"),
        Mahasiswa(nim="2301004", nama="Bagas Wijaya", email="bagas@mhs.sevima-mini.ac.id"),
    ]
    db.add_all(mahasiswa)
    db.flush()

    krs_rina = KRS(nim="2301001", status=KRSStatus.APPROVED)
    krs_doni = KRS(nim="2301002", status=KRSStatus.SUBMITTED)
    krs_siti = KRS(nim="2301003", status=KRSStatus.DRAFT)
    krs_bagas = KRS(nim="2301004", status=KRSStatus.REVISION, catatan_revisi="SKS kurang")
    db.add_all([krs_rina, krs_doni, krs_siti, krs_bagas])
    db.flush()

    db.add_all(
        [
            # Rina (APPROVED): PBO, Basis Data, Kalkulus I
            KRSDetail(krs_id=krs_rina.id, kelas_id=1),
            KRSDetail(krs_id=krs_rina.id, kelas_id=2),
            KRSDetail(krs_id=krs_rina.id, kelas_id=3),
            # Doni (SUBMITTED): PBO, Statistika
            KRSDetail(krs_id=krs_doni.id, kelas_id=1),
            KRSDetail(krs_id=krs_doni.id, kelas_id=4),
            # Siti (DRAFT): PBO, Kalkulus I (tidak disentuh saat invalidasi)
            KRSDetail(krs_id=krs_siti.id, kelas_id=1),
            KRSDetail(krs_id=krs_siti.id, kelas_id=3),
            # Bagas (REVISION): Basis Data (tidak disentuh saat invalidasi)
            KRSDetail(krs_id=krs_bagas.id, kelas_id=2),
        ]
    )

    # Jadwal awal: memuat 1 room_conflict (#12 & #15) dan 1 lecturer_conflict (#17 & #21)
    jadwal = [
        Jadwal(
            id=12,
            kelas_id=1,
            hari=1,
            jam_mulai=time(8, 0),
            jam_selesai=time(10, 0),
            ruangan_kode="A101",
            dosen_id=1,
        ),
        Jadwal(
            id=15,
            kelas_id=2,
            hari=1,
            jam_mulai=time(8, 0),
            jam_selesai=time(10, 0),
            ruangan_kode="A101",
            dosen_id=2,
        ),
        Jadwal(
            id=17,
            kelas_id=3,
            hari=2,
            jam_mulai=time(10, 0),
            jam_selesai=time(12, 0),
            ruangan_kode="A102",
            dosen_id=3,
        ),
        Jadwal(
            id=21,
            kelas_id=4,
            hari=2,
            jam_mulai=time(10, 0),
            jam_selesai=time(12, 0),
            ruangan_kode="B201",
            dosen_id=3,
        ),
        Jadwal(
            id=25,
            kelas_id=5,
            hari=4,
            jam_mulai=time(8, 0),
            jam_selesai=time(10, 0),
            ruangan_kode="C301",
            dosen_id=1,
        ),
    ]
    db.add_all(jadwal)
    db.commit()
    return {"seeded": 1, "jadwal_count": len(jadwal)}
