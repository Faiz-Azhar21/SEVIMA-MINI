"""Pengujian State Machine KRS (4 x 4 x 3 = 48 kombinasi: 6 sah, 42 ilegal) & KRSInvalidator."""

from __future__ import annotations

import itertools

import pytest
from sqlalchemy import select

from app.krs.invalidator import KRSInvalidator
from app.krs.models import (
    Actor,
    IllegalKRSTransitionError,
    KRS,
    KRSStatus,
    TRANSITIONS,
)

ALL_COMBINATIONS = list(
    itertools.product(list(KRSStatus), list(KRSStatus), list(Actor))
)

VALID_COMBINATIONS = {
    (src, dst, actor)
    for (src, actor), dsts in TRANSITIONS.items()
    for dst in dsts
}

ILLEGAL_COMBINATIONS = [
    combo for combo in ALL_COMBINATIONS if combo not in VALID_COMBINATIONS
]


def test_jumlah_kombinasi_matriks_transisi():
    """Sesuai Slide 12: 4 status x 4 target x 3 aktor = 48 kombinasi (6 sah, 42 ilegal)."""
    assert len(ALL_COMBINATIONS) == 48
    assert len(VALID_COMBINATIONS) == 6
    assert len(ILLEGAL_COMBINATIONS) == 42


@pytest.mark.parametrize("src,dst,actor", sorted(VALID_COMBINATIONS, key=lambda x: tuple(i.value for i in x)))
def test_transisi_krs_sah(src: KRSStatus, dst: KRSStatus, actor: Actor):
    krs = KRS(nim="2301001", status=src)
    krs.transition(dst, actor)
    assert krs.status == dst


@pytest.mark.parametrize("src,dst,actor", ILLEGAL_COMBINATIONS)
def test_transisi_krs_ilegal_ditolak(src: KRSStatus, dst: KRSStatus, actor: Actor):
    krs = KRS(nim="2301001", status=src)
    with pytest.raises(IllegalKRSTransitionError):
        krs.transition(dst, actor)
    assert krs.status == src


def test_krs_invalidator_hanya_ubah_submitted_dan_approved_tanpa_commit(db):
    """KRSInvalidator mengembalikan SUBMITTED/APPROVED ke REVISION, membiarkan DRAFT/REVISION,
    dan tidak memanggil commit sendiri (mengikuti transaksi pemanggil).
    """
    inv = KRSInvalidator(db)
    # Kelas 1 (PBO) diambil Rina (APPROVED), Doni (SUBMITTED), Siti (DRAFT)
    terdampak = inv.invalidate(kelas_id=1, alasan="Jadwal berubah")
    nims = {k.nim for k in terdampak}
    assert nims == {"2301001", "2301002"}

    for k in terdampak:
        assert k.status == KRSStatus.REVISION
        assert k.catatan_revisi == "Otomatis: Jadwal berubah"

    siti = db.scalar(select(KRS).where(KRS.nim == "2301003"))
    assert siti is not None and siti.status == KRSStatus.DRAFT

    bagas = db.scalar(select(KRS).where(KRS.nim == "2301004"))
    assert bagas is not None and bagas.status == KRSStatus.REVISION
    assert bagas.catatan_revisi == "SKS kurang"  # Tidak tertimpa

    # Buktikan KRSInvalidator tidak commit sendiri: rollback mengembalikan status awal
    db.rollback()
    rina_after_rollback = db.scalar(select(KRS).where(KRS.nim == "2301001"))
    assert rina_after_rollback is not None
    assert rina_after_rollback.status == KRSStatus.APPROVED
