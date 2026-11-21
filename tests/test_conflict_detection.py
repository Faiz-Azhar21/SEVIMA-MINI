"""Pengujian Deteksi Bentrok 3 Dimensi, Interval Tree, & Capacity Check (Deliverable 1)."""

from __future__ import annotations

import random
from datetime import time

import pytest

from app.krs.models import KRS, KRSDetail, KRSStatus, Mahasiswa
from app.scheduling.conflict import (
    CapacityExceededError,
    IntervalTree,
    ScheduleConflictError,
    cek_kapasitas,
    detect_schedule_conflict,
)
from app.scheduling.models import Jadwal
from app.scheduling.schemas import JadwalIn


def _slot(
    jid: int,
    hari: int,
    mulai: time,
    selesai: time,
    ruangan: str,
    dosen: int,
    kelas: int | None = None,
) -> Jadwal:
    return Jadwal(
        id=jid,
        kelas_id=kelas if kelas is not None else jid,
        hari=hari,
        jam_mulai=mulai,
        jam_selesai=selesai,
        ruangan_kode=ruangan,
        dosen_id=dosen,
    )


def test_interval_setengah_terbuka_berbatasan_tidak_bentrok():
    """Selesai jam 10:00 tidak boleh dianggap bentrok dengan mulai jam 10:00."""
    j1 = _slot(1, 1, time(8, 0), time(10, 0), "A101", 1, kelas=1)
    j2 = _slot(2, 1, time(10, 0), time(12, 0), "A101", 1, kelas=2)
    assert detect_schedule_conflict([j1, j2]) == []


def test_deteksi_semua_jenis_bentrok():
    """Mendeteksi room_conflict, lecturer_conflict, dan time_overlap."""
    schedules = [
        # Pasangan room_conflict (ruang A101 sama, dosen beda)
        _slot(1, 1, time(8, 0), time(10, 0), "A101", 1, kelas=1),
        _slot(2, 1, time(9, 0), time(11, 0), "A101", 2, kelas=2),
        # Pasangan lecturer_conflict (dosen 3 sama, ruang beda)
        _slot(3, 2, time(10, 0), time(12, 0), "A102", 3, kelas=3),
        _slot(4, 2, time(11, 0), time(13, 0), "B201", 3, kelas=4),
        # Pasangan time_overlap (kelas 5 sama, ruang & dosen beda)
        _slot(5, 3, time(13, 0), time(15, 0), "A101", 4, kelas=5),
        _slot(6, 3, time(14, 0), time(16, 0), "C301", 5, kelas=5),
    ]
    conflicts = detect_schedule_conflict(schedules)
    by_type = {(c.type, c.affected) for c in conflicts}
    assert ("room_conflict", (1, 2)) in by_type
    assert ("lecturer_conflict", (3, 4)) in by_type
    assert ("time_overlap", (5, 6)) in by_type
    assert len(conflicts) == 3


def test_interval_tree_konsisten_dengan_brute_force():
    """Memastikan AVL IntervalTree menghasilkan pasangan overlap identik dengan brute force."""
    rng = random.Random(42)
    intervals = []
    for i in range(60):
        start = rng.randint(480, 960)
        end = start + rng.choice([60, 90, 120, 150])
        intervals.append((i, start, end))

    # Brute force O(n^2)
    expected = set()
    for a in range(len(intervals)):
        id_a, s_a, e_a = intervals[a]
        for b in range(a + 1, len(intervals)):
            id_b, s_b, e_b = intervals[b]
            if s_a < e_b and s_b < e_a:
                expected.add((min(id_a, id_b), max(id_a, id_b)))

    # Interval Tree O(n log n + k)
    tree: IntervalTree[int] = IntervalTree()
    found = set()
    for iid, s, e in sorted(intervals, key=lambda x: (x[1], x[2], x[0])):
        for prev_id in tree.query_overlaps(s, e):
            found.add((min(prev_id, iid), max(prev_id, iid)))
        tree.insert(s, e, iid)

    assert found == expected


def test_capacity_check_kuota_dan_enrolled(db):
    """Capacity check menolak jika kuota > kapasitas ATAU mahasiswa enrolled > kapasitas."""
    # Kelas 1 punya kuota 40 -> LAB1 (kapasitas 25) harus ditolak
    with pytest.raises(CapacityExceededError):
        cek_kapasitas(db, kelas_id=1, ruangan_kode="LAB1")

    # A101 kapasitas 40 cukup untuk Kelas 1 (kuota 40, terdaftar 3)
    cek_kapasitas(db, kelas_id=1, ruangan_kode="A101")

    # Tambahkan mahasiswa enrolled ke Kelas 5 (kuota 30) sampai 41 orang -> A101 (kap. 40) ditolak
    for idx in range(41):
        nim = f"2409{idx:03d}"
        mhs = Mahasiswa(nim=nim, nama=f"Mhs {idx}", email=f"mhs{idx}@test.ac.id")
        db.add(mhs)
        db.flush()
        krs = KRS(nim=nim, status=KRSStatus.APPROVED)
        db.add(krs)
        db.flush()
        db.add(KRSDetail(krs_id=krs.id, kelas_id=5))
    db.commit()

    with pytest.raises(CapacityExceededError):
        cek_kapasitas(db, kelas_id=5, ruangan_kode="A101")


def test_create_jadwal_bentrok_ditolak_409(service_bundle):
    """SchedulingService.create menolak jadwal baru yang bentrok dengan jadwal DB."""
    svc = service_bundle["svc"]
    # Jadwal #25 ada di Kamis (4) 08:00-10:00 C301 dosen 1
    with pytest.raises(ScheduleConflictError):
        svc.create(
            JadwalIn(
                kelas_id=5,
                hari=4,
                jam_mulai=time(9, 0),
                jam_selesai=time(11, 0),
                ruangan_kode="C301",
                dosen_id=2,
            )
        )
