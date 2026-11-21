"""Implementasi repositori SQLAlchemy untuk Observer (PesertaRepo & DosenRepo)."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.krs.models import KRS, KRSDetail
from app.scheduling.models import Dosen


class SqlPesertaRepo:
    """Mencari daftar NIM mahasiswa peserta suatu kelas dari tabel KRS/KRSDetail."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def nim_by_kelas(self, kelas_id: int) -> list[str]:
        db = self._session_factory()
        try:
            stmt = (
                select(KRS.nim)
                .join(KRSDetail, KRSDetail.krs_id == KRS.id)
                .where(KRSDetail.kelas_id == kelas_id)
                .distinct()
                .order_by(KRS.nim)
            )
            return list(db.scalars(stmt))
        finally:
            db.close()


class SqlDosenRepo:
    """Mencari kontak email dosen pengampu berdasarkan ``dosen_id``."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def kontak_by_id(self, dosen_id: int) -> str:
        db = self._session_factory()
        try:
            dosen = db.get(Dosen, dosen_id)
            if dosen is None:
                return f"dosen-{dosen_id}@sevima-mini.ac.id"
            return f"{dosen.nama} <{dosen.email}>"
        finally:
            db.close()
