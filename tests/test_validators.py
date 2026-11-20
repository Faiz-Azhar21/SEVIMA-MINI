"""Unit tests untuk Chain of Responsibility dan 4 Validator KRS."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import time

import pytest
from sqlalchemy.orm import Session

from app.models import KRS, KRSDetail, KRSStatus, MataKuliah
from app.validators import (
    ConflictValidator,
    DuplicateValidator,
    KRSContext,
    PrerequisiteValidator,
    SKSValidator,
    ValidationResult,
    Validator,
    bentrok,
    build_chain,
)


def _dummy_mk(
    kode: str,
    nama: str,
    sks: int = 3,
    hari: int = 1,
    mulai: time = time(8, 0),
    selesai: time = time(10, 30),
) -> MataKuliah:
    return MataKuliah(
        kode_mk=kode,
        nama=nama,
        sks=sks,
        hari=hari,
        jam_mulai=mulai,
        jam_selesai=selesai,
    )


def _detail_of(mk: MataKuliah) -> KRSDetail:
    return KRSDetail(kode_mk=mk.kode_mk, matakuliah=mk)


def test_validation_result_is_immutable() -> None:
    res = ValidationResult(True)
    with pytest.raises(FrozenInstanceError):
        res.ok = False  # type: ignore[misc]


def test_validator_abc_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        Validator()  # type: ignore[abstract]


def test_build_chain_rejects_empty_list() -> None:
    with pytest.raises(ValueError, match="tidak boleh kosong"):
        build_chain([])


def test_duplicate_validator(db_session: Session) -> None:
    mk1 = _dummy_mk("IF201", "Struktur Data")
    mk2 = _dummy_mk("IF204", "Jaringan Komputer")
    v = DuplicateValidator()

    ctx_ok = KRSContext("202401001", "20251", [_detail_of(mk1)], mk2, db_session)
    assert v.check(ctx_ok).ok is True

    ctx_dup = KRSContext("202401001", "20251", [_detail_of(mk1)], mk1, db_session)
    res = v.check(ctx_dup)
    assert res.ok is False
    assert res.message == "Sudah ada di KRS: Struktur Data"


def test_sks_validator_exact_24_allowed_and_25_rejected(db_session: Session) -> None:
    """Pastikan tidak terkena bug off-by-one: tepat 24 SKS boleh, 25 SKS ditolak."""
    existing = [_detail_of(_dummy_mk(f"MK{i}", f"MK {i}", sks=4)) for i in range(5)]  # 20 SKS
    v = SKSValidator()

    mk_4 = _dummy_mk("MK6", "MK Empat", sks=4)  # total = 24
    res_24 = v.check(KRSContext("202401001", "20251", existing, mk_4, db_session))
    assert res_24.ok is True

    existing_21 = existing + [_detail_of(_dummy_mk("MK7", "MK Satu", sks=1))]  # 21 SKS
    res_25 = v.check(KRSContext("202401001", "20251", existing_21, mk_4, db_session))
    assert res_25.ok is False
    assert res_25.message == "Total SKS 25 melebihi batas 24"


@pytest.mark.parametrize(
    ("hari_a", "mulai_a", "selesai_a", "hari_b", "mulai_b", "selesai_b", "expected"),
    [
        # 5 kasus uji resmi dari slide materi ConflictValidator
        (1, time(8, 0), time(10, 30), 1, time(9, 0), time(11, 0), True),    # sebagian
        (1, time(8, 0), time(11, 0), 1, time(9, 0), time(10, 0), True),     # di dalam
        (1, time(8, 0), time(10, 30), 1, time(8, 0), time(10, 30), True),   # persis sama
        (1, time(8, 0), time(10, 30), 1, time(10, 30), time(12, 0), False), # bersambung
        (1, time(8, 0), time(10, 30), 2, time(8, 0), time(10, 30), False),  # beda hari
    ],
)
def test_bentrok_interval_cases(
    hari_a: int,
    mulai_a: time,
    selesai_a: time,
    hari_b: int,
    mulai_b: time,
    selesai_b: time,
    expected: bool,
) -> None:
    a = _dummy_mk("A", "Basis Data", hari=hari_a, mulai=mulai_a, selesai=selesai_a)
    b = _dummy_mk("B", "Statistika", hari=hari_b, mulai=mulai_b, selesai=selesai_b)
    assert bentrok(a, b) is expected
    assert bentrok(b, a) is expected


def test_conflict_validator_message(db_session: Session) -> None:
    bd = _dummy_mk("IF202", "Basis Data", hari=1, mulai=time(8, 0), selesai=time(10, 30))
    stat = _dummy_mk("IF203", "Statistika", hari=1, mulai=time(9, 0), selesai=time(11, 0))
    v = ConflictValidator()

    res = v.check(KRSContext("202401001", "20251", [_detail_of(bd)], stat, db_session))
    assert res.ok is False
    assert res.message == "Jadwal bentrok: Statistika dengan Basis Data"


def test_prerequisite_validator_grade_mapping_and_semester_rules(db_session: Session) -> None:
    """Verifikasi query NOT EXISTS + skala_nilai:
    - Nilai A/B/C semester lalu lulus (menghindari bug perbandingan string >= 'C').
    - Nilai D/E/NULL atau baru diambil di semester aktif tidak lulus.
    - Mengulang dan lulus di semester berikutnya dianggap terpenuhi.
    """
    v = PrerequisiteValidator()
    kalk2 = db_session.get(MataKuliah, "MA201")
    sd = db_session.get(MataKuliah, "IF201")
    ai = db_session.get(MataKuliah, "IF207")
    assert kalk2 is not None and sd is not None and ai is not None

    # Budi (202401001): IF101=B (lulus), MA101=D (gagal) pada 20242
    res_budi_sd = v.check(KRSContext("202401001", "20251", [], sd, db_session))
    assert res_budi_sd.ok is True

    res_budi_kalk2 = v.check(KRSContext("202401001", "20251", [], kalk2, db_session))
    assert res_budi_kalk2.ok is False
    assert res_budi_kalk2.message == "Prasyarat tidak terpenuhi: Kalkulus I"

    # Multi-prasyarat (IF207 butuh IF201 dan MA101): Budi belum lulus keduanya
    res_budi_ai = v.check(KRSContext("202401001", "20251", [], ai, db_session))
    assert res_budi_ai.ok is False
    assert res_budi_ai.message == "Prasyarat tidak terpenuhi: Struktur Data, Kalkulus I"

    # Ani (202401002): IF101=A, MA101=C, IF201=B pada 20242 -> semua lulus termasuk nilai A & C!
    assert v.check(KRSContext("202401002", "20251", [], kalk2, db_session)).ok is True
    assert v.check(KRSContext("202401002", "20251", [], sd, db_session)).ok is True
    assert v.check(KRSContext("202401002", "20251", [], ai, db_session)).ok is True

    # Kasus semester aktif (20251): meski MA101 ada di KRS 20251 dengan nilai A, tetap tidak sah
    # untuk mengambil MA201 di semester 20251 (harus lulus di semester < 20251)
    krs_aktif = KRS(nim="202401001", semester="20251", status=KRSStatus.DRAFT)
    krs_aktif.details.append(KRSDetail(kode_mk="MA101", nilai="A"))
    db_session.add(krs_aktif)
    db_session.commit()
    assert v.check(KRSContext("202401001", "20251", [], kalk2, db_session)).ok is False

    # Kasus mengulang: Budi mengulang MA101 di 20251 dengan nilai A -> pada 20252 sah ambil MA201!
    assert v.check(KRSContext("202401001", "20252", [], kalk2, db_session)).ok is True


def test_chain_fail_fast_stops_before_next_validator(db_session: Session) -> None:
    """Pastikan Chain of Responsibility berhenti pada kegagalan pertama (tidak memanggil validator berikutnya)."""
    called = False

    class SpyValidator(Validator):
        def check(self, ctx: KRSContext) -> ValidationResult:
            nonlocal called
            called = True
            return ValidationResult(True)

    mk = _dummy_mk("IF201", "Struktur Data")
    chain = build_chain([DuplicateValidator(), SpyValidator()])
    res = chain.validate(KRSContext("202401001", "20251", [_detail_of(mk)], mk, db_session))

    assert res.ok is False
    assert "Sudah ada di KRS" in res.message
    assert called is False


def test_ocp_add_new_validator_without_modifying_existing_classes(db_session: Session) -> None:
    """Demonstrasi Open/Closed Principle: tambah aturan baru (tunggakan SPP) hanya lewat class baru."""

    class TunggakanSPPValidator(Validator):
        def __init__(self, menunggak: set[str]) -> None:
            self.menunggak = menunggak

        def check(self, ctx: KRSContext) -> ValidationResult:
            if ctx.nim in self.menunggak:
                return ValidationResult(False, "Mahasiswa masih memiliki tunggakan SPP")
            return ValidationResult(True)

    mk = _dummy_mk("IF204", "Jaringan Komputer")
    chain = build_chain([DuplicateValidator(), TunggakanSPPValidator({"202401001"})])
    res = chain.validate(KRSContext("202401001", "20251", [], mk, db_session))

    assert res.ok is False
    assert res.message == "Mahasiswa masih memiliki tunggakan SPP"
