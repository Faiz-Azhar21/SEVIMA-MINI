"""Unit test (10+ kasus parametrize) & property-based test (hypothesis) untuk domain GPA."""

from __future__ import annotations

from decimal import Decimal
import random

from hypothesis import given, strategies as st
import pytest

from app.domain.gpa import NilaiRecord, Skala, hitung_ipk, hitung_ips

# Skala sementara: minimal C (2.00) dianggap lulus (lihat ADR-005)
SKALA: dict[str, Skala] = {
    h: Skala(Decimal(b), l)
    for h, b, l in [
        ("A", "4.00", True),
        ("B", "3.00", True),
        ("C", "2.00", True),
        ("D", "1.00", False),
        ("E", "0.00", False),
    ]
}

# Skala alternatif apabila stakeholder mengonfirmasi D (1.00) dianggap lulus
SKALA_D_LULUS: dict[str, Skala] = {
    **SKALA,
    "D": Skala(Decimal("1.00"), True),
}


def r(kode: str, sks: int, huruf: str, sem: str = "20241") -> NilaiRecord:
    return NilaiRecord(kode_mk=kode, semester=sem, sks=sks, huruf=huruf)


# Studi kasus Rina (Slide 13): 2 semester, ada MK diulang (Kalkulus 1: E -> B) & nilai D
REKAMAN_RINA = [
    r("IF101", 3, "E", "20241"),
    r("IF102", 4, "A", "20241"),
    r("KU101", 2, "B", "20241"),
    r("IF101", 3, "B", "20242"),
    r("IF201", 3, "C", "20242"),
    r("IF202", 3, "D", "20242"),
]


@pytest.mark.parametrize(
    ("records", "harapan"),
    [
        # 1. Nilai sempurna (semua A)
        ([r("MK1", 3, "A"), r("MK2", 4, "A")], "4.00"),
        # 2. Mahasiswa semester awal (belum ada nilai -> return 0.00, bukan ZeroDivisionError)
        ([], "0.00"),
        # 3. MK diulang E -> B: hanya B yang dihitung
        ([r("MK1", 3, "E", "20241"), r("MK1", 3, "B", "20242")], "3.00"),
        # 4. MK diulang nilai turun (B -> C): tetap ambil nilai tertinggi (B)
        ([r("MK1", 3, "B", "20241"), r("MK1", 3, "C", "20242")], "3.00"),
        # 5. SKS MK diulang tidak dihitung dua kali: (3*3 + 3*4) / 6 = 21 / 6 = 3.50
        ([r("MK1", 3, "E", "20241"), r("MK1", 3, "B", "20242"), r("MK2", 3, "A", "20242")], "3.50"),
        # 6. Nilai E tidak dihitung pada IPK
        ([r("MK1", 3, "A"), r("MK2", 3, "E")], "4.00"),
        # 7. Nilai D tidak dihitung pada skala sementara (minimal C)
        ([r("MK1", 3, "A"), r("MK2", 3, "D")], "4.00"),
        # 8. Semua MK tidak lulus (hanya D dan E) -> 0.00
        ([r("MK1", 3, "D"), r("MK2", 3, "E")], "0.00"),
        # 9. Pembulatan ROUND_HALF_UP: (3*4 + 3*3 + 2*2) / 8 = 25 / 8 = 3.125 -> 3.13 (bukan 3.12!)
        ([r("MK1", 3, "A"), r("MK2", 3, "B"), r("MK3", 2, "C")], "3.13"),
        # 10. Pembulatan pecahan berulang: (3*3 + 3*3 + 3*2) / 9 = 24 / 9 = 2.666... -> 2.67
        ([r("MK1", 3, "B"), r("MK2", 3, "B"), r("MK3", 3, "C")], "2.67"),
        # 11. Studi kasus Rina (Slide 13): (3*3 + 4*4 + 2*3 + 3*2) / 12 = 37 / 12 = 3.0833 -> 3.08
        (REKAMAN_RINA, "3.08"),
        # 12. MK diulang tiga kali (E -> D -> A): ambil bobot tertinggi A, bukan max huruf string
        (
            [
                r("MK1", 3, "E", "20241"),
                r("MK1", 3, "D", "20242"),
                r("MK1", 3, "A", "20251"),
                r("MK2", 3, "C", "20241"),
            ],
            "3.00",
        ),
    ],
    ids=[
        "semua_A",
        "semester_awal_kosong",
        "ulang_E_ke_B",
        "ulang_turun_tetap_terbaik",
        "sks_ulang_tidak_dobel",
        "E_tidak_dihitung",
        "D_tidak_dihitung_skala_sementara",
        "semua_tidak_lulus",
        "pembulatan_3_125_half_up",
        "pembulatan_2_666",
        "studi_kasus_rina",
        "ulang_tiga_kali_ambil_terbaik",
    ],
)
def test_ipk(records: list[NilaiRecord], harapan: str) -> None:
    hasil = hitung_ipk(records, SKALA)
    assert isinstance(hasil, Decimal)
    assert hasil == Decimal(harapan)


@pytest.mark.parametrize(
    ("records", "semester", "harapan"),
    [
        # IPS semester 20241 Rina: E ikut dihitung -> (3*0 + 4*4 + 2*3) / 9 = 22 / 9 = 2.44
        (REKAMAN_RINA, "20241", "2.44"),
        # IPS semester 20242 Rina: hanya semester target -> (3*3 + 3*2 + 3*1) / 9 = 18 / 9 = 2.00
        (REKAMAN_RINA, "20242", "2.00"),
        # Semester belum ada nilai -> 0.00
        (REKAMAN_RINA, "20251", "0.00"),
        # Semua nilai E pada satu semester -> 0.00 (total SKS > 0)
        ([r("MK1", 3, "E", "20241"), r("MK2", 2, "E", "20241")], "20241", "0.00"),
    ],
    ids=[
        "ips_termasuk_E",
        "ips_hanya_semester_target",
        "ips_semester_kosong",
        "ips_semua_E",
    ],
)
def test_ips(records: list[NilaiRecord], semester: str, harapan: str) -> None:
    hasil = hitung_ips(records, semester, SKALA)
    assert isinstance(hasil, Decimal)
    assert hasil == Decimal(harapan)


def test_tukar_skala_D_lulus_sebagai_data() -> None:
    """Aturan kelulusan berupa data: jika D diluluskan, IPK Rina berubah dari 3.08 -> 2.67."""
    assert hitung_ipk(REKAMAN_RINA, SKALA) == Decimal("3.08")
    assert hitung_ipk(REKAMAN_RINA, SKALA_D_LULUS) == Decimal("2.67")
    assert hitung_ipk(REKAMAN_RINA, SKALA) - hitung_ipk(REKAMAN_RINA, SKALA_D_LULUS) == Decimal("0.41")


# ---------------------------------------------------------------------------
# Property-based tests (Hypothesis) — 3 invarian utama (Slide 16)
# ---------------------------------------------------------------------------
KODE_SKS = {"MK1": 2, "MK2": 3, "MK3": 4, "MK4": 3, "MK5": 2}

rekaman_strategy = st.builds(
    lambda k, sem, h: NilaiRecord(k, sem, KODE_SKS[k], h),
    st.sampled_from(list(KODE_SKS)),
    st.sampled_from(["20241", "20242", "20251"]),
    st.sampled_from(list(SKALA)),
)


@given(st.lists(rekaman_strategy, max_size=20))
def test_ipk_antara_0_dan_4(rs: list[NilaiRecord]) -> None:
    ipk = hitung_ipk(rs, SKALA)
    assert Decimal("0.00") <= ipk <= Decimal("4.00")


@given(st.lists(rekaman_strategy, max_size=20), st.sampled_from(list(KODE_SKS)))
def test_tambah_A_tidak_menurunkan(rs: list[NilaiRecord], kode: str) -> None:
    baru = NilaiRecord(kode, "20251", KODE_SKS[kode], "A")
    assert hitung_ipk([*rs, baru], SKALA) >= hitung_ipk(rs, SKALA)


@given(st.lists(rekaman_strategy, max_size=20), st.randoms())
def test_urutan_tidak_berpengaruh(rs: list[NilaiRecord], rng: random.Random) -> None:
    acak = list(rs)
    rng.shuffle(acak)
    assert hitung_ipk(acak, SKALA) == hitung_ipk(rs, SKALA)
