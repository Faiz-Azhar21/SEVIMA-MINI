"""Endpoint REST API untuk modul PMB (Penerimaan Mahasiswa Baru)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import ApproveOut, RegisterIn, RegisterOut, RejectOut, StatsOut, StatusOut
from app.services.pmb_service import PMBService

router = APIRouter(prefix="/api/pmb", tags=["PMB"])


def get_pmb_service(db: Session = Depends(get_db)) -> PMBService:
    """Dependency Injection untuk menyediakan instance PMBService per request."""
    return PMBService(db)


@router.post(
    "/register",
    response_model=RegisterOut,
    status_code=status.HTTP_201_CREATED,
    summary="Daftar calon mahasiswa baru",
    description="Mendaftarkan calon mahasiswa dengan status awal `pending` setelah validasi input.",
    responses={
        400: {"description": "Data input tidak valid (format email/telepon atau prodi/jalur tidak valid)"},
        409: {"description": "Email sudah terdaftar"},
    },
)
def register_calon_mahasiswa(
    payload: RegisterIn,
    service: PMBService = Depends(get_pmb_service),
) -> RegisterOut:
    """Endpoint pendaftaran calon mahasiswa baru."""
    return service.register(payload)


@router.get(
    "/status/{calon_id}",
    response_model=StatusOut,
    status_code=status.HTTP_200_OK,
    summary="Cek status pendaftaran",
    description="Mengembalikan status pendaftaran dan NIM (jika sudah approved) tanpa mengekspos data pribadi.",
    responses={
        404: {"description": "Pendaftar tidak ditemukan"},
    },
)
def get_registration_status(
    calon_id: int,
    service: PMBService = Depends(get_pmb_service),
) -> StatusOut:
    """Endpoint cek status pendaftaran calon mahasiswa."""
    return service.get_status(calon_id)


@router.put(
    "/approve/{calon_id}",
    response_model=ApproveOut,
    status_code=status.HTTP_200_OK,
    summary="Approve pendaftar & generate NIM",
    description=(
        "Menyetujui pendaftar berstatus `pending` menjadi `approved`, mencatat `approved_at` (UTC), "
        "dan menghasilkan NIM secara atomik & idempotent."
    ),
    responses={
        400: {"description": "Data pendaftar tidak valid untuk pembuatan NIM (mis. kode prodi bukan 3 digit)"},
        404: {"description": "Pendaftar tidak ditemukan"},
        409: {"description": "Status bukan pending (sudah rejected) atau konflik concurrency"},
    },
)
def approve_calon_mahasiswa(
    calon_id: int,
    service: PMBService = Depends(get_pmb_service),
) -> ApproveOut:
    """Endpoint admin untuk menyetujui pendaftar dan meng-generate NIM."""
    return service.approve(calon_id)


@router.put(
    "/reject/{calon_id}",
    response_model=RejectOut,
    status_code=status.HTTP_200_OK,
    summary="Reject pendaftar",
    description="Menolak pendaftar berstatus `pending` menjadi `rejected` (terminal state).",
    responses={
        404: {"description": "Pendaftar tidak ditemukan"},
        409: {"description": "Pendaftar sudah approved sehingga tidak dapat ditolak"},
    },
)
def reject_calon_mahasiswa(
    calon_id: int,
    service: PMBService = Depends(get_pmb_service),
) -> RejectOut:
    """Endpoint admin untuk menolak pendaftar."""
    return service.reject(calon_id)


@router.get(
    "/stats",
    response_model=StatsOut,
    status_code=status.HTTP_200_OK,
    summary="Dashboard statistik jumlah pendaftar",
    description="Menampilkan total pendaftar, rincian per status, per program studi, dan per jalur masuk.",
)
def get_pmb_stats(
    service: PMBService = Depends(get_pmb_service),
) -> StatsOut:
    """Endpoint dashboard statistik pendaftar PMB."""
    return service.get_stats()
