"""Unit tests untuk Chain of Responsibility & keempat Validator KRS."""

from datetime import time

from app.models import KRSDetail, Matakuliah, RiwayatNilai
from app.validators import (
    ConflictValidator,
    DuplicateValidator,
    KRSContext,
    PrerequisiteValidator,
    SKSValidator,
    build_validation_chain,
    is_schedule_conflict,
)


def _mk(
    kode: str,
    sks: int = 3,
    hari: int = 1,
    mulai: int = 8,
    selesai: int = 10,
    kode_induk: str | None = None,
) -> Matakuliah:
    return Matakuliah(
        kode_mk=kode,
        kode_induk=kode_induk or kode,
        nama=f"Matakuliah {kode}",
        sks=sks,
        hari=hari,
        jam_mulai=time(mulai, 0),
        jam_selesai=time(selesai, 0),
    )


class TestSKSValidator:
    def test_tepat_24_sks_lolos(self):
        details = [KRSDetail(matakuliah=_mk(f"MK{i}", sks=3)) for i in range(7)]  # 21 SKS
        ctx = KRSContext("2026001", details, _mk("MK8", sks=3), db=None)
        res = SKSValidator().validate(ctx)
        assert res.ok is True
        assert res.passed is True

    def test_lebih_dari_24_sks_gagal(self):
        details = [KRSDetail(matakuliah=_mk(f"MK{i}", sks=3)) for i in range(8)]  # 24 SKS
        ctx = KRSContext("2026001", details, _mk("MK9", sks=1), db=None)
        res = SKSValidator().validate(ctx)
        assert res.ok is False
        assert "24" in res.message


class TestConflictValidator:
    def test_jam_persis_sama_bentrok(self):
        a = _mk("A", hari=1, mulai=8, selesai=10)
        b = _mk("B", hari=1, mulai=8, selesai=10)
        assert is_schedule_conflict(a, b) is True

    def test_overlap_parsial_bentrok(self):
        a = _mk("A", hari=1, mulai=8, selesai=10)
        b = _mk("B", hari=1, mulai=9, selesai=11)
        assert is_schedule_conflict(a, b) is True

    def test_bersebelahan_tidak_bentrok(self):
        a = _mk("A", hari=1, mulai=8, selesai=10)
        b = _mk("B", hari=1, mulai=10, selesai=12)
        assert is_schedule_conflict(a, b) is False

    def test_hari_berbeda_tidak_bentrok(self):
        a = _mk("A", hari=1, mulai=8, selesai=10)
        b = _mk("B", hari=2, mulai=8, selesai=10)
        assert is_schedule_conflict(a, b) is False

    def test_conflict_validator_pesan_jelas(self):
        details = [KRSDetail(matakuliah=_mk("BD1", hari=1, mulai=8, selesai=10))]
        ctx = KRSContext("2026001", details, _mk("PBO1", hari=1, mulai=9, selesai=11), db=None)
        res = ConflictValidator().validate(ctx)
        assert res.ok is False
        assert "Jadwal bentrok" in res.message
        assert "Senin" in res.message


class TestDuplicateValidator:
    def test_kode_mk_sama_ditolak(self):
        details = [KRSDetail(matakuliah=_mk("BD1"))]
        ctx = KRSContext("2026001", details, _mk("BD1"), db=None)
        res = DuplicateValidator().validate(ctx)
        assert res.ok is False
        assert "double enrollment" in res.message.lower()

    def test_kelas_paralel_berbeda_kode_induk_sama_ditolak(self):
        details = [KRSDetail(matakuliah=_mk("PBO1", hari=1, kode_induk="PBO1"))]
        ctx = KRSContext(
            "2026001", details, _mk("PBO1-B", hari=3, kode_induk="PBO1"), db=None
        )
        res = DuplicateValidator().validate(ctx)
        assert res.ok is False
        assert "kelas lain" in res.message.lower()


class TestPrerequisiteValidator:
    def test_prasyarat_belum_diambil_gagal(self, db_session, seed_data):
        kal2 = seed_data["courses"]["KAL2"]
        ctx = KRSContext("2026001", [], kal2, db=db_session, semester=3)
        res = PrerequisiteValidator().validate(ctx)
        assert res.ok is False
        assert res.message == "Prasyarat tidak terpenuhi: Kalkulus I"

    def test_prasyarat_nilai_D_gagal(self, db_session, seed_data):
        db_session.add(
            RiwayatNilai(nim="2026001", kode_mk="KAL1", semester=1, nilai_huruf="D")
        )
        db_session.commit()
        kal2 = seed_data["courses"]["KAL2"]
        ctx = KRSContext("2026001", [], kal2, db=db_session, semester=3)
        res = PrerequisiteValidator().validate(ctx)
        assert res.ok is False
        assert "Kalkulus I" in res.message

    def test_prasyarat_di_semester_sama_gagal(self, db_session, seed_data):
        # Harus lulus di semester SEBELUMNYA (< semester 3)
        db_session.add(
            RiwayatNilai(nim="2026001", kode_mk="KAL1", semester=3, nilai_huruf="A")
        )
        db_session.commit()
        kal2 = seed_data["courses"]["KAL2"]
        ctx = KRSContext("2026001", [], kal2, db=db_session, semester=3)
        res = PrerequisiteValidator().validate(ctx)
        assert res.ok is False

    def test_prasyarat_mengulang_lulus_nilai_C_lolos(self, db_session, seed_data):
        db_session.add_all(
            [
                RiwayatNilai(nim="2026001", kode_mk="KAL1", semester=1, nilai_huruf="D"),
                RiwayatNilai(nim="2026001", kode_mk="KAL1", semester=2, nilai_huruf="C"),
            ]
        )
        db_session.commit()
        kal2 = seed_data["courses"]["KAL2"]
        ctx = KRSContext("2026001", [], kal2, db=db_session, semester=3)
        res = PrerequisiteValidator().validate(ctx)
        assert res.ok is True


class TestChainOfResponsibility:
    def test_rantai_berhenti_pada_kegagalan_pertama(self, db_session, seed_data):
        # MK gagal SKS (>24) DAN gagal prasyarat -> rantai harus berhenti di SKSValidator
        details = [KRSDetail(matakuliah=_mk(f"MK{i}", sks=4, hari=6)) for i in range(6)]  # 24 SKS
        kal2 = seed_data["courses"]["KAL2"]
        ctx = KRSContext("2026001", details, kal2, db=db_session, semester=3)

        chain = build_validation_chain()
        res = chain.handle(ctx)
        assert res.ok is False
        assert "24 SKS" in res.message

    def test_double_enrollment_tidak_salah_dilaporkan_sebagai_bentrok(self):
        # MK yang sama persis harus lolos ConflictValidator dan ditangkap DuplicateValidator
        mk = _mk("BD1", sks=3, hari=1, mulai=8, selesai=10)
        details = [KRSDetail(matakuliah=mk)]
        ctx = KRSContext("2026001", details, mk, db=None)

        chain = build_validation_chain()
        res = chain.handle(ctx)
        assert res.ok is False
        assert "double enrollment" in res.message.lower()
