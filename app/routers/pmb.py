from typing import List, Dict, Any
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.program_studi import ProgramStudi
from app.models.jalur_masuk import JalurMasuk
from app.schemas.pmb import (
    CalonMahasiswaCreate,
    CalonMahasiswaResponse,
    ApproveResponse,
    StatsResponse,
    ProgramStudiResponse,
    JalurMasukResponse
)
from app.services.pmb_service import (
    register_calon_mahasiswa,
    get_calon_mahasiswa_by_id,
    approve_calon_mahasiswa,
    get_pmb_statistics
)

router = APIRouter(tags=["Penerimaan Mahasiswa Baru (PMB)"])

@router.post(
    "/register",
    response_model=CalonMahasiswaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Daftar Calon Mahasiswa Baru",
    description="Mendaftarkan calon mahasiswa baru dengan validasi data email, nomor HP Indonesia, prodi, dan jalur masuk."
)
def register(data: CalonMahasiswaCreate, db: Session = Depends(get_db)):
    calon = register_calon_mahasiswa(data=data, db=db)
    return calon

@router.get(
    "/status/{calon_id}",
    response_model=CalonMahasiswaResponse,
    summary="Cek Status Pendaftaran",
    description="Melihat data pendaftaran dan status calon mahasiswa berdasarkan ID pendaftar."
)
def get_status(calon_id: int, db: Session = Depends(get_db)):
    calon = get_calon_mahasiswa_by_id(calon_id=calon_id, db=db)
    return calon

@router.put(
    "/approve/{calon_id}",
    response_model=ApproveResponse,
    summary="Approve Pendaftaran & Generate NIM",
    description="Admin menyetujui pendaftaran calon mahasiswa dan menghasilkan NIM institusional unik secara otomatis (idempotent)."
)
def approve_registration(calon_id: int, db: Session = Depends(get_db)):
    calon = approve_calon_mahasiswa(calon_id=calon_id, db=db)
    return ApproveResponse(
        id=calon.id,
        nama_lengkap=calon.nama_lengkap,
        status=calon.status.value if hasattr(calon.status, "value") else str(calon.status),
        nim=calon.nim,
        approved_at=calon.approved_at,
        message="Pendaftaran berhasil disetujui dan NIM berhasil digenerate."
    )

@router.get(
    "/stats",
    response_model=StatsResponse,
    summary="Dashboard Statistik PMB",
    description="Menampilkan statistik jumlah pendaftar keseluruhan, per status, per program studi, dan per jalur masuk."
)
def get_stats(db: Session = Depends(get_db)):
    return get_pmb_statistics(db=db)

@router.get(
    "/prodi",
    response_model=List[ProgramStudiResponse],
    summary="Daftar Program Studi",
    description="Mengambil daftar program studi yang tersedia."
)
def list_prodi(db: Session = Depends(get_db)):
    return db.query(ProgramStudi).order_by(ProgramStudi.kode.asc()).all()

@router.get(
    "/jalur",
    response_model=List[JalurMasukResponse],
    summary="Daftar Jalur Masuk",
    description="Mengambil daftar jalur masuk yang tersedia (SNBP, SNBT, Mandiri)."
)
def list_jalur(db: Session = Depends(get_db)):
    return db.query(JalurMasuk).order_by(JalurMasuk.id.asc()).all()

@router.get(
    "/list",
    response_model=List[CalonMahasiswaResponse],
    summary="Daftar Seluruh Calon Mahasiswa",
    description="Mengambil seluruh calon mahasiswa yang telah mendaftar."
)
def list_all(db: Session = Depends(get_db)):
    from app.models.calon_mahasiswa import CalonMahasiswa
    return db.query(CalonMahasiswa).order_by(CalonMahasiswa.id.desc()).all()
