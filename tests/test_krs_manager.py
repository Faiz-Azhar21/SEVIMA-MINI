"""Unit & integration tests untuk KRSManager Service."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import KRS, KRSDetail, KRSStatus
from app.services import (
    KRSError,
    KRSManager,
    KRSNotFoundError,
    KRSStateError,
    KRSValidationError,
)
from app.validators import KRSContext, ValidationResult, Validator, default_validators


def test_add_and_remove_course_happy_path(db_session: Session) -> None:
    mgr = KRSManager(db_session, default_validators(), semester="20251")

    detail = mgr.add_course("202401001", "IF201")  # Budi lulus IF101 -> sah ambil IF201
    assert detail.kode_mk == "IF201"

    krs = mgr.get_krs("202401001")
    assert krs.status == KRSStatus.DRAFT
    assert [d.kode_mk for d in krs.details] == ["IF201"]

    mgr.remove_course("202401001", "IF201")
    krs_after = mgr.get_krs("202401001")
    assert krs_after.details == []


def test_add_course_allows_adjacent_schedule_and_rejects_overlap(db_session: Session) -> None:
    """MA101 (Senin 08:00-10:30) + IF101 (Senin 10:30-13:00) bersambung -> boleh.
    IF203 (Senin 09:00-11:00) bertumpuk dengan keduanya -> ditolak.
    """
    mgr = KRSManager(db_session, default_validators(), semester="20251")
    mgr.add_course("202401001", "MA101")
    mgr.add_course("202401001", "IF101")  # bersambung 10:30 -> sah

    with pytest.raises(KRSValidationError, match="Jadwal bentrok: Statistika"):
        mgr.add_course("202401001", "IF203")


def test_add_course_rejects_missing_prerequisite_and_preserves_atomicity(db_session: Session) -> None:
    mgr = KRSManager(db_session, default_validators(), semester="20251")

    with pytest.raises(KRSValidationError, match="Prasyarat tidak terpenuhi: Kalkulus I"):
        mgr.add_course("202401001", "MA201")

    # Karena atomik (rollback pada kegagalan), KRS belum menyimpan item apapun
    krs_rows = db_session.scalars(
        select(KRS).where(KRS.nim == "202401001", KRS.semester == "20251")
    ).all()
    assert krs_rows == []


def test_add_course_rejects_exceeding_24_sks(db_session: Session) -> None:
    """Ani (202401002) mengambil 24 SKS (sah), lalu mencoba tambah MK 2 SKS -> ditolak (26 > 24)."""
    mgr = KRSManager(db_session, default_validators(), semester="20251")
    # 3+3+4+4+4+4+2 = 24 SKS (semua beda jadwal & prasyarat terpenuhi oleh Ani)
    for kode in ["MA201", "IF202", "IF201", "IF205", "IF206", "IF207", "IF208"]:
        mgr.add_course("202401002", kode)

    krs = mgr.get_krs("202401002")
    assert sum(d.matakuliah.sks for d in krs.details) == 24

    with pytest.raises(KRSValidationError, match="Total SKS 26 melebihi batas 24"):
        mgr.add_course("202401002", "IF209")


def test_add_course_rejects_duplicate_and_unknown_entities(db_session: Session) -> None:
    mgr = KRSManager(db_session, default_validators(), semester="20251")
    mgr.add_course("202401001", "IF204")

    with pytest.raises(KRSValidationError, match="Sudah ada di KRS: Jaringan Komputer"):
        mgr.add_course("202401001", "IF204")

    with pytest.raises(KRSNotFoundError, match="tidak ditemukan"):
        mgr.add_course("202401001", "UNKNOWN")

    with pytest.raises(KRSNotFoundError, match="belum disetujui PMB"):
        mgr.add_course("999999999", "IF204")


def test_status_guard_blocks_submitted_and_approved_allows_revision(db_session: Session) -> None:
    """Hanya DRAFT dan REVISION yang boleh diubah; SUBMITTED dan APPROVED ditolak."""
    mgr = KRSManager(db_session, default_validators(), semester="20251")

    # Citra (202401003) di-seed berstatus SUBMITTED
    with pytest.raises(KRSStateError, match=r"KRS \(SUBMITTED\) tidak bisa diubah"):
        mgr.add_course("202401003", "IF204")

    with pytest.raises(KRSStateError, match=r"KRS \(SUBMITTED\) tidak bisa diubah"):
        mgr.remove_course("202401003", "MA101")

    # Ubah ke APPROVED -> tetap ditolak
    krs_citra = db_session.scalar(
        select(KRS).where(KRS.nim == "202401003", KRS.semester == "20251")
    )
    assert krs_citra is not None
    krs_citra.status = KRSStatus.APPROVED
    db_session.commit()

    with pytest.raises(KRSStateError, match=r"KRS \(APPROVED\) tidak bisa diubah"):
        mgr.add_course("202401003", "IF204")

    # Ubah ke REVISION -> diperbolehkan lagi
    krs_citra.status = KRSStatus.REVISION
    db_session.commit()
    detail = mgr.add_course("202401003", "IF204")
    assert detail.kode_mk == "IF204"


def test_db_unique_constraint_safety_net_on_integrity_error(db_session: Session) -> None:
    """Jika validator aplikasi dilewati (validator palsu selalu True),
    UNIQUE(krs_id, kode_mk) tetap menangkap duplikat, rollback, dan mengembalikan pesan ramah.
    """

    class AlwaysPassValidator(Validator):
        def check(self, ctx: KRSContext) -> ValidationResult:
            return ValidationResult(True)

    mgr = KRSManager(db_session, [AlwaysPassValidator()], semester="20251")
    mgr.add_course("202401001", "IF204")

    with pytest.raises(KRSValidationError, match="Sudah ada di KRS: Jaringan Komputer"):
        mgr.add_course("202401001", "IF204")


def test_validate_krs_collects_all_errors_at_once(db_session: Session) -> None:
    """`validate_krs()` harus mengumpulkan SEMUA masalah sekaligus (collect-all)
    tanpa terhenti di kegagalan pertama dan tanpa duplikasi pesan bentrok simetris.
    """
    # Masukkan langsung data KRS bermasalah untuk mensimulasikan 3 pelanggaran sekaligus:
    # 1. MA201 -> prasyarat Kalkulus I belum lulus oleh Budi
    # 2. IF202 (Senin 08:00-10:30) & IF203 (Senin 09:00-11:00) -> jadwal bentrok
    # 3. Total SKS > 24 (total 27 SKS)
    krs = KRS(nim="202401001", semester="20251", status=KRSStatus.DRAFT)
    for kode in ["MA201", "IF202", "IF203", "IF201", "IF205", "IF206", "IF207", "IF208"]:
        # 3+3+3+4+4+4+4+2 = 27 SKS
        krs.details.append(KRSDetail(kode_mk=kode))
    db_session.add(krs)
    db_session.commit()

    mgr = KRSManager(db_session, default_validators(), semester="20251")
    issues = mgr.validate_krs("202401001")
    messages = [r.message for r in issues]

    # Harus melaporkan SKS, prasyarat, dan jadwal bentrok sekaligus!
    assert any("Total SKS 27 melebihi batas 24" in m for m in messages)
    assert any("Prasyarat tidak terpenuhi: Kalkulus I" in m for m in messages)
    bentrok_msgs = [m for m in messages if m.startswith("Jadwal bentrok:")]
    assert len(bentrok_msgs) == 1  # Bentrok simetris IF202 <-> IF203 hanya dilaporkan sekali


def test_remove_course_error_cases_and_week6_stubs(db_session: Session) -> None:
    mgr = KRSManager(db_session, default_validators(), semester="20251")

    with pytest.raises(KRSNotFoundError, match="belum ada"):
        mgr.remove_course("202401001", "IF201")

    mgr.add_course("202401001", "IF201")
    with pytest.raises(KRSNotFoundError, match="tidak ada di KRS"):
        mgr.remove_course("202401001", "IF204")

    with pytest.raises(NotImplementedError):
        mgr.submit_krs("202401001")

    with pytest.raises(NotImplementedError):
        mgr.approve_krs("202401001", dosen_pa_id=1)

    # Semua exception khusus merupakan turunan KRSError
    assert issubclass(KRSValidationError, KRSError)
    assert issubclass(KRSStateError, KRSError)
    assert issubclass(KRSNotFoundError, KRSError)
