"""Exhaustive tests untuk State Machine KRS (seluruh 32 kombinasi state x state x aktor).

4 kombinasi sah ditulis ulang secara manual dari dokumen tugas (bukan diimpor dari
tabel `TRANSITIONS` di kode produksi) agar bug pada tabel transisi tidak ikut tersalin.
28 kombinasi ilegal diuji lewat `pytest.mark.parametrize`.
"""

from itertools import product

import pytest

from app.enums import Actor, KRSStatus
from app.exceptions import TransitionError
from app.models import KRS

# Hardcode dari spesifikasi dokumen tugas (Step 2)
S = KRSStatus
A = Actor
SAH: set[tuple[KRSStatus, KRSStatus, Actor]] = {
    (S.DRAFT, S.SUBMITTED, A.MAHASISWA),
    (S.SUBMITTED, S.APPROVED, A.DOSEN_PA),
    (S.SUBMITTED, S.REVISION, A.DOSEN_PA),
    (S.REVISION, S.SUBMITTED, A.MAHASISWA),
}

ILEGAL: list[tuple[KRSStatus, KRSStatus, Actor]] = [
    combo for combo in product(S, S, A) if combo not in SAH
]


def test_jumlah_kombinasi_lengkap():
    assert len(SAH) == 4
    assert len(ILEGAL) == 28
    assert len(SAH) + len(ILEGAL) == 32


@pytest.mark.parametrize("asal,tujuan,aktor", sorted(SAH, key=lambda x: (x[0].value, x[1].value, x[2].value)))
def test_transisi_sah_berhasil(asal: KRSStatus, tujuan: KRSStatus, aktor: Actor):
    krs = KRS(status=asal)
    krs.transition(tujuan, aktor)
    assert krs.status == tujuan


@pytest.mark.parametrize("asal,tujuan,aktor", ILEGAL)
def test_transisi_ilegal_ditolak(asal: KRSStatus, tujuan: KRSStatus, aktor: Actor):
    krs = KRS(status=asal)
    with pytest.raises(TransitionError, match="Transisi tidak diizinkan"):
        krs.transition(tujuan, aktor)
    # Pastikan status tidak berubah saat transisi ilegal ditolak
    assert krs.status == asal


def test_draft_ke_approved_langsung_selalu_ditolak():
    for aktor in Actor:
        krs = KRS(status=KRSStatus.DRAFT)
        with pytest.raises(TransitionError, match="DRAFT ke APPROVED"):
            krs.transition(KRSStatus.APPROVED, aktor)
        assert krs.status == KRSStatus.DRAFT
