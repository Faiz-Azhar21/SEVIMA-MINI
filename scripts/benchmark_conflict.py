"""Benchmark empiris: detect_naive O(n^2) vs detect_schedule_conflict O(n log n + k).

Digunakan sebagai bukti pengukuran nyata pada ADR 001 (keputusan menunda Interval Tree).
"""

from __future__ import annotations

import random
import statistics
import time
from collections import Counter
from datetime import time as dt_time

from app.services.conflict import (
    JadwalSlot,
    detect_naive,
    detect_schedule_conflict,
)


def generate_dataset(n: int, seed: int = 42) -> list[JadwalSlot]:
    """Bangkitkan dataset jadwal realistis (6 hari, ruang & dosen proporsional)."""
    rng = random.Random(seed)
    jumlah_ruang = max(10, n // 30)  # ~6-8 jadwal/ruang/hari pada N=600 -> 20 ruang
    jumlah_dosen = max(15, n // 20)
    ruangan = [f"R{i:03d}" for i in range(1, jumlah_ruang + 1)]
    dataset: list[JadwalSlot] = []
    for idx in range(1, n + 1):
        hari = rng.randint(1, 6)
        jam_mulai = rng.randint(7, 16)
        menit_mulai = rng.choice((0, 20, 40))
        durasi_menit = rng.choice((50, 100, 150))
        total_selesai = jam_mulai * 60 + menit_mulai + durasi_menit
        selesai_jam, selesai_menit = divmod(min(total_selesai, 21 * 60), 60)
        dataset.append(
            JadwalSlot(
                id=idx,
                hari=hari,
                jam_mulai=dt_time(jam_mulai, menit_mulai),
                jam_selesai=dt_time(selesai_jam, selesai_menit),
                ruangan_kode=rng.choice(ruangan),
                dosen_id=rng.randint(1, jumlah_dosen),
            )
        )
    return dataset


def benchmark(sizes: tuple[int, ...] = (40, 200, 600, 2000, 5000), runs: int = 5) -> None:
    print(
        f"{'N':>6} | {'Pasangan':>10} | {'Konflik':>8} | "
        f"{'Naif (ms)':>11} | {'Sweep (ms)':>11} | {'Speedup':>8} | Sama?"
    )
    print("-" * 78)
    for n in sizes:
        data = generate_dataset(n)
        naive_times: list[float] = []
        sweep_times: list[float] = []
        res_naive = []
        res_sweep = []
        for _ in range(runs):
            t0 = time.perf_counter()
            res_naive = detect_naive(data)
            naive_times.append((time.perf_counter() - t0) * 1000)

            t0 = time.perf_counter()
            res_sweep = detect_schedule_conflict(data)
            sweep_times.append((time.perf_counter() - t0) * 1000)

        sama = Counter(res_naive) == Counter(res_sweep)
        med_naive = statistics.median(naive_times)
        med_sweep = statistics.median(sweep_times)
        speedup = med_naive / med_sweep if med_sweep > 0 else 0.0
        pasangan = n * (n - 1) // 2
        print(
            f"{n:>6} | {pasangan:>10,} | {len(res_sweep):>8,} | "
            f"{med_naive:>11.3f} | {med_sweep:>11.3f} | {speedup:>7.1f}x | {sama}"
        )


if __name__ == "__main__":
    benchmark()
