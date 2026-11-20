"""Integration tests untuk KRSManager Service, Transaksi ACID, Otorisasi 2 Lapis, & Locking."""

from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.enums import KRSStatus
from app.exceptions import (
    ForbiddenError,
    KRSError,
    KRSLockedError,
    TransitionError,
    ValidationInputError,
)
from app.models import KRS, LogKRS, Notifikasi, RiwayatNilai
from app.service import KRSManager


def test_tambah_mk_tanpa_prasyarat_error(manager: KRSManager, seed_data):
    """Test wajib dokumen tugas: tambah MK tanpa prasyarat -> error dengan pesan jelas."""
    rina = seed_data["rina"]
    kal2 = seed_data["courses"]["KAL2"]
    with pytest.raises(KRSError, match="Prasyarat tidak terpenuhi: Kalkulus I"):
        manager.add_course(rina.nim, kal2.kode_mk)


def test_jadwal_bentrok_error(manager: KRSManager, seed_data):
    """Test wajib dokumen tugas: bentrok jadwal (Senin 08:00) -> error."""
    rina = seed_data["rina"]
    bd = seed_data["courses"]["BD1"]
    pbo = seed_data["courses"]["PBO1"]

    manager.add_course(rina.nim, bd.kode_mk)
    with pytest.raises(KRSError, match="Jadwal bentrok"):
        manager.add_course(rina.nim, pbo.kode_mk)


def test_double_enrollment_error(manager: KRSManager, seed_data):
    rina = seed_data["rina"]
    manager.add_course(rina.nim, "PBO1")

    with pytest.raises(KRSError, match="double enrollment"):
        manager.add_course(rina.nim, "PBO1")

    # Kelas paralel lain dari MK induk yang sama juga ditolak
    with pytest.raises(KRSError, match="kelas lain"):
        manager.add_course(rina.nim, "PBO1-B")


def test_batas_sks_24_dan_remove_course(manager: KRSManager, seed_data):
    budi = seed_data["budi"]
    # KAL2(3) + BD1(3) + PBO1-B(3) + ALGO(4) + JARKOM(4) + SO1(4) + AI1(3) = 24 SKS (pas)
    for kode in ["KAL2", "BD1", "PBO1-B", "ALGO", "JARKOM", "SO1", "AI1"]:
        krs = manager.add_course(budi.nim, kode)
    assert krs.total_sks == 24

    # Tambah GAME1 (3 SKS) -> 27 SKS -> gagal
    with pytest.raises(KRSError, match="24 SKS"):
        manager.add_course(budi.nim, "GAME1")

    # Hapus AI1 (3 SKS) -> 21 SKS, lalu tambah GAME1 (3 SKS) -> 24 SKS -> sukses
    krs = manager.remove_course(budi.nim, "AI1")
    assert krs.total_sks == 21
    krs = manager.add_course(budi.nim, "GAME1")
    assert krs.total_sks == 24


def test_submit_krs_kosong_ditolak(manager: KRSManager, seed_data):
    rina = seed_data["rina"]
    with pytest.raises(KRSError, match="KRS kosong"):
        manager.submit_krs(rina.nim)


def test_submit_krs_memvalidasi_ulang_jika_nilai_berubah(
    db_session, manager: KRSManager, seed_data
):
    """Jika nilai semester lalu dikoreksi menjadi D setelah add_course,
    submit_krs wajib mendeteksi dan menolak pengajuan."""
    budi = seed_data["budi"]
    manager.add_course(budi.nim, "KAL2")  # Awalnya lolos karena nilai KAL1 = B

    # Simulasi koreksi nilai di database menjadi D
    riwayat = db_session.execute(
        select(RiwayatNilai).where(
            RiwayatNilai.nim == budi.nim, RiwayatNilai.kode_mk == "KAL1"
        )
    ).scalar_one()
    riwayat.nilai_huruf = "D"
    db_session.commit()

    with pytest.raises(KRSError, match="Prasyarat tidak terpenuhi: Kalkulus I"):
        manager.submit_krs(budi.nim)


def test_siklus_hidup_lengkap_draft_submitted_revision_approved(
    db_session, manager: KRSManager, seed_data
):
    rina = seed_data["rina"]
    manager.add_course(rina.nim, "BD1")
    manager.add_course(rina.nim, "PBO1-B")

    # 1. Mahasiswa submit -> SUBMITTED
    krs = manager.submit_krs(rina.nim)
    assert krs.status == KRSStatus.SUBMITTED
    assert krs.submitted_at is not None

    # Saat SUBMITTED, add/remove terkunci
    with pytest.raises(KRSLockedError, match="tidak bisa diubah"):
        manager.add_course(rina.nim, "ALGO")
    with pytest.raises(KRSLockedError, match="tidak bisa diubah"):
        manager.remove_course(rina.nim, "BD1")

    # 2. Dosen PA minta revisi -> REVISION
    krs = manager.revise_krs(rina.nim, dosen_pa_id=101, catatan="Tambahkan MK Algoritma")
    assert krs.status == KRSStatus.REVISION
    assert krs.catatan_revisi == "Tambahkan MK Algoritma"

    # Saat REVISION, mahasiswa boleh mengedit lagi
    krs = manager.add_course(rina.nim, "ALGO")
    assert krs.total_sks == 10

    # 3. Mahasiswa submit ulang -> SUBMITTED
    krs = manager.submit_krs(rina.nim)
    assert krs.status == KRSStatus.SUBMITTED

    # 4. Dosen PA approve -> APPROVED (tercatat waktu, LogKRS, dan Notifikasi)
    krs = manager.approve_krs(rina.nim, dosen_pa_id=101, expected_version=krs.version)
    assert krs.status == KRSStatus.APPROVED
    assert krs.approved_at is not None

    logs = db_session.execute(select(LogKRS).where(LogKRS.krs_id == krs.id)).scalars().all()
    assert [l.aksi for l in logs] == ["submit", "revise", "submit", "approve"]

    notifs = db_session.execute(
        select(Notifikasi).where(Notifikasi.nim == rina.nim)
    ).scalars().all()
    assert len(notifs) == 2
    assert any("disetujui" in n.pesan for n in notifs)

    # Setelah APPROVED (status akhir), tidak bisa diedit atau diubah lagi
    with pytest.raises(KRSLockedError):
        manager.add_course(rina.nim, "AI1")
    with pytest.raises(TransitionError):
        manager.submit_krs(rina.nim)


def test_otorisasi_dua_lapis_dosen_pa_lain_ditolak(manager: KRSManager, seed_data):
    rina = seed_data["rina"]
    manager.add_course(rina.nim, "BD1")
    manager.submit_krs(rina.nim)

    # Dosen PA Rina adalah 101; dosen 999 tidak berwenang
    with pytest.raises(ForbiddenError, match="bukan dosen PA"):
        manager.approve_krs(rina.nim, dosen_pa_id=999)

    with pytest.raises(ForbiddenError, match="bukan dosen PA"):
        manager.revise_krs(rina.nim, dosen_pa_id=999, catatan="Coba tolak")


def test_revise_tanpa_catatan_ditolak(manager: KRSManager, seed_data):
    rina = seed_data["rina"]
    manager.add_course(rina.nim, "BD1")
    manager.submit_krs(rina.nim)

    with pytest.raises(ValidationInputError, match="Catatan revisi wajib diisi"):
        manager.revise_krs(rina.nim, dosen_pa_id=101, catatan="   ")


def test_approve_transaksi_acid_rollback_jika_gagal_di_tengah(
    db_session, manager: KRSManager, seed_data
):
    """Membuktikan Atomicity (ACID): jika error terjadi saat commit/penulisan
    notifikasi, seluruh perubahan (status APPROVED, approved_at, LogKRS) dibatalkan."""
    rina = seed_data["rina"]
    manager.add_course(rina.nim, "BD1")
    manager.submit_krs(rina.nim)

    with patch.object(db_session, "commit", side_effect=RuntimeError("Simulasi DB error")):
        with pytest.raises(RuntimeError, match="Simulasi DB error"):
            manager.approve_krs(rina.nim, dosen_pa_id=101)

    # Pastikan semua dibatalkan (tidak ada data setengah jadi)
    krs = db_session.get(KRS, rina.id)
    assert krs.status == KRSStatus.SUBMITTED
    assert krs.approved_at is None
    approve_logs = db_session.execute(
        select(LogKRS).where(LogKRS.krs_id == rina.id, LogKRS.aksi == "approve")
    ).scalars().all()
    assert len(approve_logs) == 0
    notifs = db_session.execute(
        select(Notifikasi).where(Notifikasi.nim == rina.nim)
    ).scalars().all()
    assert len(notifs) == 0


def test_optimistic_lock_version_naik_dan_deteksi_layar_basi(
    manager: KRSManager, seed_data
):
    """Mensimulasikan layar basi: dosen melihat KRS pada versi lama, lalu mahasiswa
    menambah MK di REVISION & submit ulang sehingga versi naik -> approve versi lama ditolak 409."""
    rina = seed_data["rina"]
    krs_awal = manager.add_course(rina.nim, "BD1")
    versi_sebelum_ubah = krs_awal.version

    # Menambah MK kedua HARUS menaikkan kolom version (sentuh diubah_pada)
    krs_setelah_tambah = manager.add_course(rina.nim, "ALGO")
    assert krs_setelah_tambah.version > versi_sebelum_ubah

    krs_submitted = manager.submit_krs(rina.nim)
    versi_basi = krs_submitted.version - 1

    with pytest.raises(KRSLockedError, match="KRS sudah berubah, muat ulang"):
        manager.approve_krs(rina.nim, dosen_pa_id=101, expected_version=versi_basi)
