"""Integration tests untuk GradeService, dua penjaga (pengampu & presensi), FK DB, dan audit trail."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.akademik import KRS, KRSDetail
from app.models.nilai import GradeHistory
from app.ports.presensi import PresensiStub
from app.repositories.nilai_repo import NilaiRepo
from app.services.grade_service import (
    GradeForbiddenError,
    GradeNotFoundError,
    GradeService,
    GradeValidationError,
    is_pengampu,
)


def test_is_pengampu_memeriksa_tabel_jadwal(db_session: Session) -> None:
    assert is_pengampu(db_session, dosen_id=1, kelas_id=5) is True
    assert is_pengampu(db_session, dosen_id=2, kelas_id=5) is False


def test_non_pengampu_ditolak_403(db_session: Session, presensi_stub: PresensiStub) -> None:
    svc = GradeService(db_session, presensi_stub)
    with pytest.raises(GradeForbiddenError) as exc_info:
        svc.input_nilai(dosen_id=2, kelas_id=5, nim="2025004", huruf="A")
    assert exc_info.value.status_code == 403


def test_mahasiswa_tidak_terdaftar_di_kelas_ditolak_404(
    db_session: Session, presensi_stub: PresensiStub
) -> None:
    svc = GradeService(db_session, presensi_stub)
    with pytest.raises(GradeNotFoundError) as exc_info:
        svc.input_nilai(dosen_id=1, kelas_id=5, nim="9999999", huruf="A")
    assert exc_info.value.status_code == 404


def test_presensi_dibawah_75_ditolak_400(db_session: Session, presensi_stub: PresensiStub) -> None:
    # Budi (2025002) memiliki presensi 70% di kelas 5 (Basis Data A)
    svc = GradeService(db_session, presensi_stub)
    with pytest.raises(GradeValidationError, match="75%"):
        svc.input_nilai(dosen_id=1, kelas_id=5, nim="2025002", huruf="B")

    # Juga uji boundary ketat 74.99%
    stub_ketat = PresensiStub({("2025004", 5): Decimal("74.99")})
    svc_ketat = GradeService(db_session, stub_ketat)
    with pytest.raises(GradeValidationError, match="75%"):
        svc_ketat.input_nilai(dosen_id=1, kelas_id=5, nim="2025004", huruf="A")


def test_presensi_tepat_75_diperbolehkan_dan_mencatat_history_awal(
    db_session: Session, presensi_stub: PresensiStub
) -> None:
    # Dimas (2025004) presensi tepat 75%, nilai awal NULL
    svc = GradeService(db_session, presensi_stub)
    detail = svc.input_nilai(dosen_id=1, kelas_id=5, nim="2025004", huruf="B")
    assert detail.nilai == "B"

    riwayat = db_session.scalars(
        select(GradeHistory).where(GradeHistory.grade_id == detail.id)
    ).all()
    assert len(riwayat) == 1
    assert riwayat[0].old_value is None
    assert riwayat[0].new_value == "B"
    assert riwayat[0].changed_by == 1
    assert riwayat[0].reason is None


def test_input_huruf_sama_idempotent_tanpa_tambah_history(
    db_session: Session, presensi_stub: PresensiStub
) -> None:
    svc = GradeService(db_session, presensi_stub)
    # Sari (2025003) di kelas 5 sudah bernilai C (1 baris history awal)
    detail = db_session.scalar(
        select(KRSDetail).join(KRS).where(KRS.nim == "2025003", KRSDetail.kelas_id == 5)
    )
    assert detail is not None
    jumlah_awal = len(
        db_session.scalars(select(GradeHistory).where(GradeHistory.grade_id == detail.id)).all()
    )

    svc.input_nilai(dosen_id=1, kelas_id=5, nim="2025003", huruf="C")
    jumlah_akhir = len(
        db_session.scalars(select(GradeHistory).where(GradeHistory.grade_id == detail.id)).all()
    )
    assert jumlah_akhir == jumlah_awal


def test_edit_nilai_tanpa_alasan_ditolak_dan_dengan_alasan_tercatat_di_view(
    db_session: Session, presensi_stub: PresensiStub
) -> None:
    svc = GradeService(db_session, presensi_stub)

    # Tanpa alasan atau spasi saja -> 400
    with pytest.raises(GradeValidationError, match="alasan"):
        svc.input_nilai(dosen_id=1, kelas_id=5, nim="2025003", huruf="A", alasan=None)
    with pytest.raises(GradeValidationError, match="alasan"):
        svc.input_nilai(dosen_id=1, kelas_id=5, nim="2025003", huruf="A", alasan="   ")

    # Dengan alasan sah -> berhasil dan tercatat di view v_riwayat_nilai
    detail = svc.input_nilai(
        dosen_id=1,
        kelas_id=5,
        nim="2025003",
        huruf="A",
        alasan="Revisi nilai UAS setelah koreksi ulang",
    )
    assert detail.nilai == "A"

    repo = NilaiRepo(db_session)
    rows = repo.riwayat_nilai("2025003")
    assert len(rows) >= 2
    terbaru = rows[0]
    assert terbaru.old_value == "C"
    assert terbaru.new_value == "A"
    assert terbaru.pengubah == "Dr. Hendra Wijaya"
    assert terbaru.reason == "Revisi nilai UAS setelah koreksi ulang"


def test_huruf_asing_ditolak_oleh_service_dan_foreign_key_database(
    db_session: Session, presensi_stub: PresensiStub
) -> None:
    svc = GradeService(db_session, presensi_stub)
    with pytest.raises(GradeValidationError):
        svc.input_nilai(dosen_id=1, kelas_id=5, nim="2025004", huruf="A+")

    # Pembuktian langsung di level database: PRAGMA foreign_keys=ON menolak huruf tak dikenal
    detail = db_session.scalar(
        select(KRSDetail).join(KRS).where(KRS.nim == "2025004", KRSDetail.kelas_id == 5)
    )
    assert detail is not None
    detail.nilai = "Z"
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
