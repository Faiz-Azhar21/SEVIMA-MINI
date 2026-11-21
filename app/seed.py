"""Seed data dummy SEVIMA-Mini (bebas data pribadi mahasiswa asli sesuai AI-First Charter)."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.akademik import Dosen, Jadwal, Kelas, KRS, KRSDetail, Mahasiswa, MataKuliah
from app.models.nilai import GradeHistory, SkalaNilai, VIEW_RIWAYAT_NILAI_SQL

DEFAULT_SKALA_NILAI: list[tuple[str, Decimal, bool]] = [
    ("A", Decimal("4.00"), True),
    ("B", Decimal("3.00"), True),
    ("C", Decimal("2.00"), True),
    # Asumsi sementara: minimal C (2.00) untuk lulus; D menunggu konfirmasi stakeholder (lihat ADR-005).
    ("D", Decimal("1.00"), False),
    ("E", Decimal("0.00"), False),
]


def ensure_view_riwayat_nilai(db: Session) -> None:
    """Pastikan SQL view v_riwayat_nilai tersedia pada database."""
    db.execute(text("DROP VIEW IF EXISTS v_riwayat_nilai"))
    db.execute(text(VIEW_RIWAYAT_NILAI_SQL))
    db.commit()


def default_presensi_map() -> dict[tuple[str, int], Decimal]:
    """Data presensi dummy untuk PresensiStub (kelas_id 5 = Basis Data A)."""
    return {
        ("2025001", 5): Decimal("92"),  # Rina: >= 75% (boleh)
        ("2025002", 5): Decimal("70"),  # Budi: < 75% (terkunci)
        ("2025003", 5): Decimal("81"),  # Sari: >= 75% (boleh)
        ("2025004", 5): Decimal("75"),  # Dimas: tepat 75% (boundary, masih boleh)
    }


def seed_dummy_data(db: Session) -> None:
    """Isi data dummy idempoten untuk demo form web dan verifikasi awal."""
    ensure_view_riwayat_nilai(db)

    if db.scalar(select(SkalaNilai).limit(1)) is None:
        for huruf, bobot, lulus in DEFAULT_SKALA_NILAI:
            db.add(SkalaNilai(huruf=huruf, bobot=bobot, lulus=lulus))
        db.flush()

    if db.scalar(select(Mahasiswa).limit(1)) is not None:
        db.commit()
        return

    # Mahasiswa dummy (bukan data asli)
    mahasiswa_list = [
        Mahasiswa(nim="2025001", nama="Rina", prodi="Teknik Informatika", angkatan=2024),
        Mahasiswa(nim="2025002", nama="Budi", prodi="Teknik Informatika", angkatan=2024),
        Mahasiswa(nim="2025003", nama="Sari", prodi="Teknik Informatika", angkatan=2024),
        Mahasiswa(nim="2025004", nama="Dimas", prodi="Teknik Informatika", angkatan=2025),
    ]
    db.add_all(mahasiswa_list)

    # Dosen dummy
    d1 = Dosen(id=1, nidn="0011018801", nama="Dr. Hendra Wijaya")
    d2 = Dosen(id=2, nidn="0022029002", nama="Dr. Ratna Sari")
    db.add_all([d1, d2])

    # Mata kuliah dummy (sesuai studi kasus Rina di Slide 13)
    mk_list = [
        MataKuliah(kode_mk="IF101", nama_mk="Kalkulus 1", sks=3),
        MataKuliah(kode_mk="IF102", nama_mk="Algoritma", sks=4),
        MataKuliah(kode_mk="KU101", nama_mk="Bahasa Inggris", sks=2),
        MataKuliah(kode_mk="IF201", nama_mk="Struktur Data", sks=3),
        MataKuliah(kode_mk="IF202", nama_mk="Basis Data", sks=3),
    ]
    db.add_all(mk_list)
    db.flush()

    # Kelas dummy
    kelas_list = [
        Kelas(id=1, kode_mk="IF101", nama_kelas="Kalkulus 1 A", semester="20241"),
        Kelas(id=2, kode_mk="IF102", nama_kelas="Algoritma A", semester="20241"),
        Kelas(id=3, kode_mk="KU101", nama_kelas="Bahasa Inggris A", semester="20241"),
        Kelas(id=4, kode_mk="IF101", nama_kelas="Kalkulus 1 (Ulang)", semester="20242"),
        Kelas(id=5, kode_mk="IF202", nama_kelas="Basis Data A", semester="20242"),
        Kelas(id=6, kode_mk="IF201", nama_kelas="Struktur Data A", semester="20242"),
    ]
    db.add_all(kelas_list)
    db.flush()

    # Jadwal pengampu (Minggu 7): Dosen 1 mengampu kelas 1, 4, 5; Dosen 2 mengampu kelas 2, 3, 6
    jadwal_list = [
        Jadwal(kelas_id=1, dosen_id=1, ruangan="R-101", hari="Senin", jam_mulai="08:00", jam_selesai="10:30"),
        Jadwal(kelas_id=2, dosen_id=2, ruangan="R-102", hari="Selasa", jam_mulai="08:00", jam_selesai="11:20"),
        Jadwal(kelas_id=3, dosen_id=2, ruangan="R-103", hari="Rabu", jam_mulai="10:00", jam_selesai="11:40"),
        Jadwal(kelas_id=4, dosen_id=1, ruangan="R-101", hari="Senin", jam_mulai="13:00", jam_selesai="15:30"),
        Jadwal(kelas_id=5, dosen_id=1, ruangan="Lab-BD", hari="Kamis", jam_mulai="08:00", jam_selesai="10:30"),
        Jadwal(kelas_id=6, dosen_id=2, ruangan="Lab-SD", hari="Jumat", jam_mulai="08:00", jam_selesai="10:30"),
    ]
    db.add_all(jadwal_list)

    # KRS Rina (20241 & 20242 -> IPS 20241 = 2.44, IPS 20242 = 2.00, IPK = 3.08)
    krs_rina_1 = KRS(nim="2025001", semester="20241", status="APPROVED")
    krs_rina_2 = KRS(nim="2025001", semester="20242", status="APPROVED")
    krs_budi_2 = KRS(nim="2025002", semester="20242", status="APPROVED")
    krs_sari_2 = KRS(nim="2025003", semester="20242", status="APPROVED")
    krs_dimas_2 = KRS(nim="2025004", semester="20242", status="APPROVED")
    db.add_all([krs_rina_1, krs_rina_2, krs_budi_2, krs_sari_2, krs_dimas_2])
    db.flush()

    details = [
        # Rina 20241
        KRSDetail(krs_id=krs_rina_1.id, kode_mk="IF101", kelas_id=1, nilai="E"),
        KRSDetail(krs_id=krs_rina_1.id, kode_mk="IF102", kelas_id=2, nilai="A"),
        KRSDetail(krs_id=krs_rina_1.id, kode_mk="KU101", kelas_id=3, nilai="B"),
        # Rina 20242
        KRSDetail(krs_id=krs_rina_2.id, kode_mk="IF101", kelas_id=4, nilai="B"),
        KRSDetail(krs_id=krs_rina_2.id, kode_mk="IF201", kelas_id=6, nilai="C"),
        KRSDetail(krs_id=krs_rina_2.id, kode_mk="IF202", kelas_id=5, nilai="D"),
        # Budi 20242 (presensi 70% di Basis Data A, belum ada nilai)
        KRSDetail(krs_id=krs_budi_2.id, kode_mk="IF202", kelas_id=5, nilai=None),
        # Sari 20242 (presensi 81% di Basis Data A, nilai lama C)
        KRSDetail(krs_id=krs_sari_2.id, kode_mk="IF202", kelas_id=5, nilai="C"),
        # Dimas 20242 (mahasiswa baru, presensi tepat 75% di Basis Data A, belum ada nilai)
        KRSDetail(krs_id=krs_dimas_2.id, kode_mk="IF202", kelas_id=5, nilai=None),
    ]
    db.add_all(details)
    db.flush()

    # Catat audit trail awal untuk nilai yang sudah terisi saat seed
    pengampu_map = {1: 1, 2: 2, 3: 2, 4: 1, 5: 1, 6: 2}
    for d in details:
        if d.nilai is not None:
            db.add(
                GradeHistory(
                    grade_id=d.id,
                    old_value=None,
                    new_value=d.nilai,
                    changed_by=pengampu_map[d.kelas_id],
                    reason="Input nilai awal semester",
                )
            )

    db.commit()
