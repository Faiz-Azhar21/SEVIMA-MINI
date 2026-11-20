"""Script untuk mengisi data contoh (mahasiswa, matakuliah, prasyarat, riwayat nilai)
ke database lokal (`sevima_krs.db`) agar API langsung bisa dicoba lewat Swagger UI.

Jalankan dengan:
    python -m app.seed
"""

from datetime import time

from sqlalchemy import select

from app.database import SessionLocal, init_db
from app.enums import JenisMK, KRSStatus
from app.models import KRS, Matakuliah, Prerequisite, RiwayatNilai


def seed_demo_data() -> None:
    """Mengisi data demo secara idempoten (aman dijalankan berulang kali)."""
    init_db()
    db = SessionLocal()
    try:
        courses = [
            Matakuliah(
                kode_mk="KAL1", kode_induk="KAL1", kelas="A", nama="Kalkulus I",
                sks=3, hari=1, jam_mulai=time(13, 0), jam_selesai=time(15, 0), jenis=JenisMK.WAJIB,
            ),
            Matakuliah(
                kode_mk="KAL2", kode_induk="KAL2", kelas="A", nama="Kalkulus II",
                sks=3, hari=2, jam_mulai=time(8, 0), jam_selesai=time(10, 0), jenis=JenisMK.WAJIB,
            ),
            Matakuliah(
                kode_mk="BD1", kode_induk="BD1", kelas="A", nama="Basis Data",
                sks=3, hari=1, jam_mulai=time(8, 0), jam_selesai=time(10, 0), jenis=JenisMK.WAJIB,
            ),
            Matakuliah(
                kode_mk="PBO1", kode_induk="PBO1", kelas="A", nama="Pemrograman Berorientasi Objek",
                sks=3, hari=1, jam_mulai=time(8, 0), jam_selesai=time(10, 0), jenis=JenisMK.WAJIB,
            ),
            Matakuliah(
                kode_mk="PBO1-B", kode_induk="PBO1", kelas="B", nama="Pemrograman Berorientasi Objek",
                sks=3, hari=3, jam_mulai=time(10, 0), jam_selesai=time(12, 0), jenis=JenisMK.WAJIB,
            ),
            Matakuliah(
                kode_mk="ALGO", kode_induk="ALGO", kelas="A", nama="Algoritma & Struktur Data",
                sks=4, hari=2, jam_mulai=time(10, 0), jam_selesai=time(12, 0), jenis=JenisMK.WAJIB,
            ),
            Matakuliah(
                kode_mk="AI1", kode_induk="AI1", kelas="A", nama="Kecerdasan Buatan",
                sks=3, hari=5, jam_mulai=time(13, 0), jam_selesai=time(15, 0), jenis=JenisMK.PILIHAN,
            ),
            Matakuliah(
                kode_mk="ML1", kode_induk="ML1", kelas="A", nama="Machine Learning",
                sks=3, hari=1, jam_mulai=time(8, 0), jam_selesai=time(10, 0), jenis=JenisMK.PILIHAN,
            ),
        ]
        for mk in courses:
            if db.get(Matakuliah, mk.kode_mk) is None:
                db.add(mk)
        db.flush()

        # Prasyarat: KAL2 membutuhkan KAL1 (minimal C)
        if db.get(Prerequisite, ("KAL2", "KAL1")) is None:
            db.add(Prerequisite(kode_mk="KAL2", prasyarat_kode_mk="KAL1", nilai_minimal="C"))

        # Mahasiswa 1: Rina (NIM 2026001, Dosen PA 101) — belum lulus KAL1
        if db.execute(select(KRS).where(KRS.nim == "2026001", KRS.semester == 3)).scalar_one_or_none() is None:
            db.add(KRS(nim="2026001", semester=3, dosen_pa_id=101, status=KRSStatus.DRAFT))

        # Mahasiswa 2: Budi (NIM 2026002, Dosen PA 102) — sudah lulus KAL1 nilai B di semester 1
        if db.execute(select(KRS).where(KRS.nim == "2026002", KRS.semester == 3)).scalar_one_or_none() is None:
            db.add(KRS(nim="2026002", semester=3, dosen_pa_id=102, status=KRSStatus.DRAFT))
            db.add(RiwayatNilai(nim="2026002", kode_mk="KAL1", semester=1, nilai_huruf="B"))

        db.commit()
        print("Seed selesai! Data contoh siap dipakai di sevima_krs.db:")
        print("  - Mahasiswa Rina : NIM 2026001 (Dosen PA ID: 101, belum lulus KAL1)")
        print("  - Mahasiswa Budi : NIM 2026002 (Dosen PA ID: 102, sudah lulus KAL1 nilai B)")
        print("  - Kode MK        : KAL1, KAL2 (prasyarat KAL1), BD1, PBO1 (bentrok BD1), PBO1-B, ALGO, AI1, ML1")
    finally:
        db.close()


if __name__ == "__main__":
    seed_demo_data()
