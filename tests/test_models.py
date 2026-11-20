"""Unit tests untuk model ORM SQLAlchemy 2.0, arah relasi, dan database constraints."""

from __future__ import annotations

from datetime import time

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import KRS, KRSDetail, KRSStatus, MataKuliah, prerequisite


def test_self_referencing_prerequisite_direction(db_session: Session) -> None:
    """Pastikan arah primaryjoin/secondaryjoin TIDAK tertukar:
    Struktur Data membutuhkan Algoritma, bukan sebaliknya.
    """
    sd = db_session.get(MataKuliah, "IF201")
    algo = db_session.get(MataKuliah, "IF101")
    ai = db_session.get(MataKuliah, "IF207")
    kalk1 = db_session.get(MataKuliah, "MA101")

    assert sd is not None and algo is not None and ai is not None and kalk1 is not None
    assert [m.kode_mk for m in sd.prasyarat] == ["IF101"]
    assert algo.prasyarat == []
    assert sorted(m.kode_mk for m in ai.prasyarat) == ["IF201", "MA101"]


def test_check_constraint_sks_out_of_range(db_session: Session) -> None:
    """CHECK constraint menolak SKS di luar rentang 1..4."""
    mk_invalid = MataKuliah(
        kode_mk="XX999",
        nama="MK SKS Invalid",
        sks=5,
        hari=1,
        jam_mulai=time(8, 0),
        jam_selesai=time(10, 0),
    )
    db_session.add(mk_invalid)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_check_constraint_jam_mulai_must_be_before_jam_selesai(db_session: Session) -> None:
    """CHECK constraint menolak jadwal dengan jam_mulai >= jam_selesai."""
    mk_invalid = MataKuliah(
        kode_mk="XX998",
        nama="MK Jam Terbalik",
        sks=3,
        hari=2,
        jam_mulai=time(11, 0),
        jam_selesai=time(9, 0),
    )
    db_session.add(mk_invalid)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_check_constraint_prerequisite_cannot_reference_self(db_session: Session) -> None:
    """CHECK constraint menolak MK menjadi prasyarat bagi dirinya sendiri."""
    with pytest.raises(IntegrityError):
        db_session.execute(
            prerequisite.insert().values(kode_mk="IF101", kode_prasyarat="IF101")
        )
        db_session.commit()
    db_session.rollback()


def test_unique_constraint_krs_nim_semester(db_session: Session) -> None:
    """Satu mahasiswa hanya boleh memiliki satu KRS per semester."""
    db_session.add(KRS(nim="202401001", semester="20251", status=KRSStatus.DRAFT))
    db_session.commit()

    db_session.add(KRS(nim="202401001", semester="20251", status=KRSStatus.DRAFT))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_unique_constraint_krs_detail_prevents_double_enrollment(db_session: Session) -> None:
    """UNIQUE(krs_id, kode_mk) menjadi lapis pertahanan DB anti double enrollment."""
    krs = KRS(nim="202401001", semester="20251", status=KRSStatus.DRAFT)
    db_session.add(krs)
    db_session.flush()

    db_session.add(KRSDetail(krs_id=krs.id, kode_mk="MA101"))
    db_session.commit()

    db_session.add(KRSDetail(krs_id=krs.id, kode_mk="MA101"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_fk_krs_nim_rejects_unregistered_nim(db_session: Session) -> None:
    """ForeignKey krs.nim -> calon_mahasiswa.nim menolak NIM yang tidak terdaftar."""
    db_session.add(KRS(nim="999999999", semester="20251", status=KRSStatus.DRAFT))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_cascade_delete_orphan_removes_krs_detail_row(db_session: Session) -> None:
    """Melepas detail dari `krs.details` benar-benar menghapus baris dari tabel `krs_detail`."""
    krs = KRS(nim="202401001", semester="20251", status=KRSStatus.DRAFT)
    mk = db_session.get(MataKuliah, "IF204")
    assert mk is not None
    detail = KRSDetail(matakuliah=mk)
    krs.details.append(detail)
    db_session.add(krs)
    db_session.commit()
    detail_id = detail.id

    krs.details.remove(detail)
    db_session.commit()

    assert db_session.scalar(select(KRSDetail).where(KRSDetail.id == detail_id)) is None
