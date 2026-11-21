"""Integration test NilaiRepo & GPACalculator + differential test SQL CTE vs Python."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.akademik import Kelas, KRS, KRSDetail, Mahasiswa
from app.repositories.nilai_repo import NilaiRepo
from app.services.gpa_calculator import GPACalculator


def test_gpa_calculator_studi_kasus_rina_dan_mahasiswa_baru(db_session: Session) -> None:
    repo = NilaiRepo(db_session)
    calc = GPACalculator(repo)

    # Rina (2025001) — cocok dengan hitungan tangan Slide 13
    assert calc.calculate_ips("2025001", "20241") == Decimal("2.44")
    assert calc.calculate_ips("2025001", "20242") == Decimal("2.00")
    assert calc.calculate_ipk("2025001") == Decimal("3.08")

    # Budi (2025002) & Dimas (2025004) — nilai masih NULL di semester berjalan, tidak KeyError
    assert calc.calculate_ipk("2025002") == Decimal("0.00")
    assert calc.calculate_ipk("2025004") == Decimal("0.00")
    assert calc.calculate_ips("2025004", "20242") == Decimal("0.00")


def test_differential_sql_cte_sama_dengan_python(db_session: Session) -> None:
    """Differential test: versi SQL (CTE + ROW_NUMBER) harus identik dengan versi Python."""
    repo = NilaiRepo(db_session)
    calc = GPACalculator(repo)

    # Tambahkan skenario pembulatan 3.125 (25/8 -> 3.13) + MK ulang turun (B -> C) di DB
    m = Mahasiswa(nim="2025099", nama="Tono", prodi="Teknik Informatika", angkatan=2024)
    db_session.add(m)
    k1 = KRS(nim="2025099", semester="20241", status="APPROVED")
    k2 = KRS(nim="2025099", semester="20242", status="APPROVED")
    db_session.add_all([k1, k2])
    db_session.flush()

    # 3 SKS A (12) + 3 SKS B (9) + 2 SKS C (4) = 25 / 8 = 3.125 -> 3.13
    # Plus ulang IF101 turun dari A -> C (tetap ambil A) dan IF202 = NULL (diabaikan)
    db_session.add_all(
        [
            KRSDetail(krs_id=k1.id, kode_mk="IF101", kelas_id=1, nilai="A"),  # 3 SKS -> 12
            KRSDetail(krs_id=k1.id, kode_mk="IF201", kelas_id=6, nilai="B"),  # 3 SKS -> 9
            KRSDetail(krs_id=k1.id, kode_mk="KU101", kelas_id=3, nilai="C"),  # 2 SKS -> 4
            KRSDetail(krs_id=k2.id, kode_mk="IF101", kelas_id=4, nilai="C"),  # ulang turun -> abaikan
            KRSDetail(krs_id=k2.id, kode_mk="IF202", kelas_id=5, nilai=None),  # NULL -> abaikan
        ]
    )
    db_session.commit()

    # Pastikan semua mahasiswa di DB menghasilkan angka identik antara Python vs SQL CTE
    for nim in ["2025001", "2025002", "2025003", "2025004", "2025099"]:
        ipk_py = calc.calculate_ipk(nim)
        ipk_sql = repo.calculate_ipk_sql(nim)
        assert ipk_sql == ipk_py, f"Mismatch untuk {nim}: SQL={ipk_sql} vs Python={ipk_py}"

    assert calc.calculate_ipk("2025099") == Decimal("3.13")
