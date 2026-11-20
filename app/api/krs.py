"""Endpoint FastAPI tipis untuk Modul KRS.

Tanggung jawab lapisan API:
- Terima HTTP request & validasi payload via Pydantic v2.
- Delegasikan seluruh logika bisnis ke `KRSManager`.
- Terjemahkan hasil atau domain exception (`KRSError`) ke HTTP response.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.krs import KRS, KRSDetail
from app.schemas.krs import (
    AddCourseRequest,
    KRSDetailOut,
    KRSOut,
    KRSValidationOut,
    MataKuliahOut,
    MessageOut,
    ValidationIssueOut,
)
from app.services.krs_manager import (
    DEFAULT_SEMESTER,
    KRSError,
    KRSManager,
    KRSNotFoundError,
    KRSStateError,
    KRSValidationError,
)
from app.validators.krs import default_validators

router = APIRouter(prefix="/api/krs", tags=["KRS"])


def get_krs_manager(
    semester: str = Query(default=DEFAULT_SEMESTER, min_length=5, max_length=5),
    db: Session = Depends(get_db),
) -> KRSManager:
    """Dependency factory untuk membuat KRSManager dengan validator default."""
    return KRSManager(db=db, validators=default_validators(), semester=semester)


def _to_detail_out(detail: KRSDetail) -> KRSDetailOut:
    return KRSDetailOut(
        id=detail.id,
        kode_mk=detail.kode_mk,
        nilai=detail.nilai,
        matakuliah=MataKuliahOut.model_validate(detail.matakuliah),
    )


def _to_krs_out(krs: KRS) -> KRSOut:
    details_out = [_to_detail_out(d) for d in krs.details]
    total_sks = sum(d.matakuliah.sks for d in krs.details)
    return KRSOut(
        id=krs.id,
        nim=krs.nim,
        semester=krs.semester,
        status=krs.status,
        dosen_pa_id=krs.dosen_pa_id,
        total_sks=total_sks,
        details=details_out,
    )


def _handle_krs_error(exc: KRSError) -> HTTPException:
    if isinstance(exc, KRSNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, KRSStateError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, KRSValidationError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/{nim}", response_model=KRSOut)
def get_krs(nim: str, manager: KRSManager = Depends(get_krs_manager)) -> KRSOut:
    """Ambil kartu KRS mahasiswa untuk semester aktif."""
    try:
        krs = manager.get_krs(nim)
        return _to_krs_out(krs)
    except KRSError as exc:
        raise _handle_krs_error(exc) from exc


@router.post("/{nim}/courses", response_model=KRSDetailOut, status_code=status.HTTP_201_CREATED)
def add_course(
    nim: str,
    payload: AddCourseRequest,
    manager: KRSManager = Depends(get_krs_manager),
) -> KRSDetailOut:
    """Tambahkan satu mata kuliah ke KRS mahasiswa."""
    try:
        detail = manager.add_course(nim, payload.kode_mk)
        return _to_detail_out(detail)
    except KRSError as exc:
        raise _handle_krs_error(exc) from exc


@router.delete("/{nim}/courses/{kode_mk}", response_model=MessageOut)
def remove_course(
    nim: str,
    kode_mk: str,
    manager: KRSManager = Depends(get_krs_manager),
) -> MessageOut:
    """Hapus satu mata kuliah dari KRS mahasiswa."""
    try:
        manager.remove_course(nim, kode_mk)
        return MessageOut(message=f"Mata kuliah {kode_mk} berhasil dihapus dari KRS")
    except KRSError as exc:
        raise _handle_krs_error(exc) from exc


@router.get("/{nim}/validate", response_model=KRSValidationOut)
def validate_krs(
    nim: str,
    manager: KRSManager = Depends(get_krs_manager),
) -> KRSValidationOut:
    """Validasi menyeluruh seluruh mata kuliah pada KRS (mengumpulkan semua error)."""
    try:
        issues = manager.validate_krs(nim)
        return KRSValidationOut(
            nim=nim,
            semester=manager.semester,
            valid=len(issues) == 0,
            issues=[ValidationIssueOut(ok=r.ok, message=r.message) for r in issues],
        )
    except KRSError as exc:
        raise _handle_krs_error(exc) from exc
