"""Router Integrasi KRS: Block KRS otomatis jika mahasiswa memiliki tunggakan SPP."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import KrsEnrollment, Mahasiswa
from app.schemas import KrsSubmitRequest
from app.services.billing_service import KrsBlockedError, check_krs_eligibility, submit_krs

router = APIRouter(prefix="/api/krs", tags=["KRS & Block Tunggakan"])


@router.get("/{nim}/eligibility")
def api_krs_eligibility(nim: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Mengecek apakah mahasiswa dengan NIM tertentu bebas tunggakan & boleh mengisi KRS."""
    try:
        return check_krs_eligibility(db, nim)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/submit", status_code=201)
def api_submit_krs(payload: KrsSubmitRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Submit pengisian KRS — otomatis mengembalikan 403 Forbidden jika ada tunggakan SPP."""
    try:
        return submit_krs(
            db=db,
            nim=payload.nim,
            semester=payload.semester,
            mata_kuliah=payload.mata_kuliah,
            total_sks=payload.total_sks,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KrsBlockedError as exc:
        raise HTTPException(
            status_code=403,
            detail={
                "message": str(exc),
                "krs_blocked": True,
                "eligibility": exc.eligibility,
            },
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{nim}")
def list_student_krs(nim: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Melihat riwayat KRS yang berhasil disubmit mahasiswa."""
    mhs = db.execute(select(Mahasiswa).where(Mahasiswa.nim == nim)).scalar_one_or_none()
    if mhs is None:
        raise HTTPException(status_code=404, detail=f"Mahasiswa NIM '{nim}' tidak ditemukan.")

    rows = (
        db.execute(
            select(KrsEnrollment)
            .where(KrsEnrollment.mahasiswa_id == mhs.id)
            .order_by(KrsEnrollment.created_at.desc())
        )
        .scalars()
        .all()
    )
    return {
        "nim": mhs.nim,
        "nama": mhs.nama,
        "enrollments": [
            {
                "id": r.id,
                "semester": r.semester,
                "mata_kuliah": json.loads(r.mata_kuliah),
                "total_sks": r.total_sks,
                "status": r.status,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
    }
