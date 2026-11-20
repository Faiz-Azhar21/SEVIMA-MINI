"""Property-Based Testing dengan Hypothesis (Step 4 — 1000 kombinasi acak).

Menguji properti/invarian sistem validator nyata di memori (tanpa DB agar cepat
dan bebas dari masalah fixture scope):
1. `test_total_sks_never_exceeds_limit`: urutan MK acak apa pun (SKS 1-4, hingga
   40 MK) tidak pernah menghasilkan total SKS > 24, dan setiap penolakan wajib
   beralasan (`total + sks > 24`).
2. `test_mk_diterima_tidak_pernah_bentrok`: urutan jadwal acak apa pun tidak
   pernah menghasilkan dua MK diterima yang saling tumpang tindih, diverifikasi
   dengan fungsi pemeriksa terpisah (himpunan slot jam) agar bug tidak tersalin.
"""

from datetime import time

from hypothesis import given, settings, strategies as st

from app.models import KRSDetail, Matakuliah
from app.validators import ConflictValidator, KRSContext, SKSValidator

daftar_sks = st.lists(st.integers(min_value=1, max_value=4), max_size=40)

jadwal_strategy = st.tuples(
    st.integers(min_value=1, max_value=3),   # Sengaja 3 hari (Senin-Rabu) agar sering bentrok
    st.integers(min_value=7, max_value=16),  # Jam mulai 07:00 - 16:00
    st.integers(min_value=1, max_value=3),   # Durasi 1 - 3 jam
)


def _slot_jam(mk: Matakuliah) -> set[tuple[int, int]]:
    """Oracle pemeriksa terpisah (independen dari `is_schedule_conflict`):
    memecah setiap MK menjadi himpunan pasangan (hari, jam_ke)."""
    return {
        (mk.hari, jam)
        for jam in range(mk.jam_mulai.hour, mk.jam_selesai.hour)
    }


@settings(max_examples=1000, deadline=None)
@given(daftar_sks)
def test_total_sks_never_exceeds_limit(sks_list: list[int]):
    """Properti 1: No matter what courses are added, total accepted SKS <= 24,
    dan setiap penolakan memang karena total + sks > 24."""
    details: list[KRSDetail] = []
    validator = SKSValidator()

    for i, sks in enumerate(sks_list):
        mk = Matakuliah(kode_mk=f"MK{i:02d}", nama=f"MK {i}", sks=sks)
        total_sebelum = sum(d.matakuliah.sks for d in details)
        ctx = KRSContext("2026001", details, mk, db=None)

        if validator.validate(ctx).ok:
            details.append(KRSDetail(kode_mk=mk.kode_mk, matakuliah=mk))
        else:
            # Assert kedua: penolakan harus beralasan (mencegah validator yang menolak semua MK)
            assert total_sebelum + sks > 24

        # Assert utama: total SKS diterima tidak pernah > 24 di setiap langkah
        assert sum(d.matakuliah.sks for d in details) <= 24


@settings(max_examples=1000, deadline=None)
@given(st.lists(jadwal_strategy, max_size=15))
def test_mk_diterima_tidak_pernah_bentrok(daftar: list[tuple[int, int, int]]):
    """Properti 2: Tidak ada dua MK yang diterima oleh ConflictValidator
    yang memiliki slot waktu tumpang tindih (diverifikasi oleh oracle terpisah)."""
    details: list[KRSDetail] = []
    validator = ConflictValidator()

    for i, (hari, jam, durasi) in enumerate(daftar):
        mk = Matakuliah(
            kode_mk=f"MK{i}",
            nama=f"MK {i}",
            sks=2,
            hari=hari,
            jam_mulai=time(jam, 0),
            jam_selesai=time(jam + durasi, 0),
        )
        ctx = KRSContext("2026001", details, mk, db=None)
        if validator.validate(ctx).ok:
            details.append(KRSDetail(kode_mk=mk.kode_mk, matakuliah=mk))
        else:
            # Penolakan wajib beralasan: ada minimal 1 slot beririsan dengan MK yang diterima
            slot_baru = _slot_jam(mk)
            assert any(slot_baru & _slot_jam(d.matakuliah) for d in details)

    # Pemeriksaan global via union himpunan slot
    all_slots = [_slot_jam(d.matakuliah) for d in details]
    total_slot_individu = sum(len(s) for s in all_slots)
    total_slot_gabungan = len(set().union(*all_slots)) if all_slots else 0
    assert total_slot_individu == total_slot_gabungan
