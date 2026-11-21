"""Example-based tests untuk detektor konflik & constraint database.

Setiap kasus parametrize menjadi penjaga permanen terhadap 5 bug klasik hasil AI:
1. Operator <= alih-alih < (kuliah bersambung 09:40 dianggap bentrok)
2. Perbandingan jam sebagai str ("9:00" > "10:00")
3. Lupa memeriksa kesamaan hari
4. Pasangan dilaporkan dua kali (A,B) dan (B,A)
5. Melaporkan 'time_overlap' sebagai konflik padahal irisan waktu saja adalah normal
"""

from __future__ import annotations

from collections import Counter
from datetime import time

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.jadwal import Jadwal
from app.services.conflict import (
    Conflict,
    JadwalSlot,
    detect_naive,
    detect_schedule_conflict,
    overlap,
)


def J(
    id: int,
    hari: int,
    mulai: str,
    selesai: str,
    ruang: str = "A101",
    dosen: int = 1,
) -> JadwalSlot:
    """Helper ringkas membentuk JadwalSlot dari teks jam ISO HH:MM."""
    return JadwalSlot(
        id=id,
        hari=hari,
        jam_mulai=time.fromisoformat(mulai),
        jam_selesai=time.fromisoformat(selesai),
        ruangan_kode=ruang,
        dosen_id=dosen,
    )


R, L = "room_conflict", "lecturer_conflict"


@pytest.mark.parametrize(
    "b,harap",
    [
        # 1. Ruangan sama, dosen beda, waktu bertumpuk -> room_conflict
        (J(2, 1, "09:00", "11:00", dosen=2), {Conflict(R, (1, 2))}),
        # 2. Dosen sama, ruangan beda, waktu bertumpuk -> lecturer_conflict
        (J(2, 1, "09:00", "11:00", ruang="B201"), {Conflict(L, (1, 2))}),
        # 3. Kuliah bersambung tepat pukul 09:40 -> BUKAN bentrok (jaga bug <=)
        (J(2, 1, "09:40", "11:20"), set()),
        # 4. Beda hari dengan ruang & dosen sama -> BUKAN bentrok (jaga bug lupa hari)
        (J(2, 2, "08:00", "09:40"), set()),
        # 5. Jadwal di dalam jadwal lain dengan ruang & dosen sama -> 2 konflik sekaligus
        (
            J(2, 1, "08:30", "09:00"),
            {Conflict(R, (1, 2)), Conflict(L, (1, 2))},
        ),
        # 6. Waktu bertumpuk tetapi ruang & dosen berbeda -> kondisi NORMAL (bukan time_overlap)
        (J(2, 1, "08:00", "09:40", ruang="B201", dosen=2), set()),
    ],
)
def test_detect_schedule_conflict_cases(b: JadwalSlot, harap: set[Conflict]) -> None:
    a = J(1, 1, "08:00", "09:40")
    hasil_sweep = detect_schedule_conflict([a, b])
    hasil_naif = detect_naive([a, b])

    assert set(hasil_sweep) == harap
    assert set(hasil_naif) == harap
    # Pastikan tidak ada pasangan ganda (A, B) & (B, A)
    assert len(hasil_sweep) == len(harap)
    assert len(hasil_naif) == len(harap)


def test_perbandingan_waktu_jam_9_dan_jam_10() -> None:
    """Menjaga bug perbandingan string: time(9, 0) < time(10, 0) harus True."""
    pagi = J(1, 1, "09:00", "10:00")
    berikutnya = J(2, 1, "10:00", "11:00")
    bertumpuk = J(3, 1, "09:30", "10:30")

    assert not overlap(pagi, berikutnya)
    assert overlap(pagi, bertumpuk)
    assert detect_schedule_conflict([pagi, berikutnya]) == []
    assert Counter(detect_schedule_conflict([pagi, bertumpuk])) == Counter(
        [Conflict(R, (1, 3)), Conflict(L, (1, 3))]
    )


def test_urutan_input_terbalik_menghasilkan_conflict_kanonik() -> None:
    """Pasangan (B, A) harus menghasilkan tuple affected terurut (1, 2), bukan (2, 1)."""
    a = J(1, 1, "08:00", "09:40")
    b = J(2, 1, "09:00", "10:40", dosen=2)

    assert detect_schedule_conflict([b, a]) == [Conflict(R, (1, 2))]
    assert detect_naive([b, a]) == [Conflict(R, (1, 2))]


def test_db_check_constraint_jam_terbalik_ditolak(
    db_session: Session, sample_entities: dict
) -> None:
    """Penjaga terakhir di level database: jam_mulai >= jam_selesai ditolak DB."""
    bad = Jadwal(
        kelas_id=sample_entities["kelas"]["bd_a"].id,
        hari=1,
        jam_mulai=time(10, 0),
        jam_selesai=time(9, 0),
        ruangan_kode="A101",
        dosen_id=sample_entities["dosen"][0].id,
    )
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_db_check_constraint_hari_di_luar_rentang_ditolak(
    db_session: Session, sample_entities: dict
) -> None:
    """Penjaga terakhir di level database: hari harus BETWEEN 1 AND 6."""
    bad = Jadwal(
        kelas_id=sample_entities["kelas"]["bd_a"].id,
        hari=7,
        jam_mulai=time(8, 0),
        jam_selesai=time(9, 40),
        ruangan_kode="A101",
        dosen_id=sample_entities["dosen"][0].id,
    )
    db_session.add(bad)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
