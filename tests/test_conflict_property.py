"""Property-based & differential testing dengan Hypothesis.

Properti 1 (Invariant):
  Simulasi admin memasukkan jadwal acak satu per satu pada ruang domain sempit
  (Senin-Rabu, 2 ruang, 3 dosen agar bentrok sering terjadi). Jadwal yang diterima
  diverifikasi dengan metode INDEPENDEN (pecah menjadi slot 1 jam + Counter),
  bukan memanggil ulang fungsi overlap().

Properti 2 (Differential Testing):
  Output detect_schedule_conflict (sort & sweep) harus identik persis dengan
  detect_naive, termasuk jumlah kemunculannya (memakai Counter, bukan set,
  sehingga bug pasangan ganda juga tertangkap).

Catatan keterbatasan:
  Generator di sini memakai jam bulat; kasus menit bersambung (mis. 09:40)
  tetap dijaga oleh example-based tests di tests/test_conflict.py.
"""

from __future__ import annotations

from collections import Counter
from datetime import time

from hypothesis import given, settings
from hypothesis import strategies as st

from app.services.conflict import (
    JadwalSlot,
    detect_naive,
    detect_schedule_conflict,
)

# Domain sengaja sempit (Senin-Rabu, 2 ruang, 3 dosen) supaya bentrok sering terjadi
satu = st.tuples(
    st.integers(1, 3),            # hari: Senin..Rabu
    st.integers(7, 16),           # jam mulai: 07..16
    st.integers(1, 3),            # durasi: 1..3 jam
    st.sampled_from(["A101", "A102"]),  # 2 ruangan
    st.integers(1, 3),            # 3 dosen
)


@settings(max_examples=500, deadline=None)
@given(st.lists(satu, max_size=15))
def test_jadwal_diterima_tidak_pernah_bentrok(
    daftar: list[tuple[int, int, int, str, int]],
) -> None:
    diterima: list[JadwalSlot] = []
    for i, (hari, jam, durasi, ruang, dosen) in enumerate(daftar):
        j = JadwalSlot(
            id=i,
            hari=hari,
            jam_mulai=time(jam, 0),
            jam_selesai=time(jam + durasi, 0),
            ruangan_kode=ruang,
            dosen_id=dosen,
        )
        if not detect_schedule_conflict(diterima + [j]):
            diterima.append(j)

    # Pemeriksa independen: pecah setiap jadwal menjadi slot 1 jam per sumber daya
    pakai = Counter(
        (j.hari, sumber, h)
        for j in diterima
        for sumber in (f"R:{j.ruangan_kode}", f"D:{j.dosen_id}")
        for h in range(j.jam_mulai.hour, j.jam_selesai.hour)
    )
    assert all(n == 1 for n in pakai.values())


@settings(max_examples=500, deadline=None)
@given(st.lists(satu, max_size=30))
def test_sweep_sama_dengan_naif(
    daftar: list[tuple[int, int, int, str, int]],
) -> None:
    jadwal = [
        JadwalSlot(
            id=i,
            hari=h,
            jam_mulai=time(j, 0),
            jam_selesai=time(j + d, 0),
            ruangan_kode=r,
            dosen_id=ds,
        )
        for i, (h, j, d, r, ds) in enumerate(daftar)
    ]
    assert Counter(detect_schedule_conflict(jadwal)) == Counter(detect_naive(jadwal))
