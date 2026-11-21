"""Dependency Injection untuk FastAPI router (database, otentikasi dosen, port presensi)."""

from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_session
from app.models.akademik import Dosen
from app.ports.presensi import PresensiPort, PresensiStub
from app.repositories.nilai_repo import NilaiRepo
from app.seed import default_presensi_map
from app.services.gpa_calculator import GPACalculator
from app.services.grade_service import GradeService

_default_presensi_stub = PresensiStub(default_presensi_map())


def get_db() -> Generator[Session, None, None]:
    yield from get_session()


def get_presensi_port() -> PresensiPort:
    """Sediakan PresensiPort (sementara memakai PresensiStub hingga Minggu 12)."""
    return _default_presensi_stub


def get_current_dosen(
    x_dosen_id: int | None = Header(default=None, alias="X-Dosen-Id"),
    db: Session = Depends(get_db),
) -> Dosen:
    """Ambil identitas dosen dari sesi/header autentikasi (bukan dari body request)."""
    if x_dosen_id is None:
        raise HTTPException(
            status_code=401,
            detail="Autentikasi diperlukan: header X-Dosen-Id tidak ditemukan",
        )
    dosen = db.get(Dosen, x_dosen_id)
    if dosen is None:
        raise HTTPException(status_code=401, detail="Identitas dosen tidak valid")
    return dosen


def get_grade_service(
    db: Session = Depends(get_db),
    presensi: PresensiPort = Depends(get_presensi_port),
) -> GradeService:
    return GradeService(db=db, presensi=presensi)


def get_nilai_repo(db: Session = Depends(get_db)) -> NilaiRepo:
    return NilaiRepo(db=db)


def get_gpa(repo: NilaiRepo = Depends(get_nilai_repo)) -> GPACalculator:
    return GPACalculator(repo=repo)
