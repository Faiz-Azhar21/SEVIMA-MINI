from datetime import datetime, timezone
from typing import Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi import HTTPException, status

from app.models.calon_mahasiswa import CalonMahasiswa, StatusPendaftaran
from app.models.program_studi import ProgramStudi
from app.models.jalur_masuk import JalurMasuk
from app.schemas.pmb import CalonMahasiswaCreate
from app.services.nim_generator import generate_nim, _nim_lock

def register_calon_mahasiswa(data: CalonMahasiswaCreate, db: Session) -> CalonMahasiswa:
    # 1. Check duplicate email (Constraint: unique email -> 409 Conflict)
    existing_student = db.query(CalonMahasiswa).filter(CalonMahasiswa.email == data.email).first()
    if existing_student:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Email '{data.email}' sudah terdaftar dalam sistem PMB."
        )

    # 2. Check program studi existence
    prodi = db.query(ProgramStudi).filter(ProgramStudi.id == data.program_studi_id).first()
    if not prodi:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Program Studi dengan ID {data.program_studi_id} tidak ditemukan."
        )

    # 3. Resolve jalur masuk
    jalur = None
    if data.jalur_masuk:
        jalur = db.query(JalurMasuk).filter(
            func.upper(JalurMasuk.kode) == data.jalur_masuk.upper()
        ).first()
    elif data.jalur_masuk_id:
        jalur = db.query(JalurMasuk).filter(JalurMasuk.id == data.jalur_masuk_id).first()

    if not jalur:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Jalur masuk harus diisi dan valid (pilihan: SNBP, SNBT, Mandiri)."
        )

    new_calon = CalonMahasiswa(
        nama_lengkap=data.nama_lengkap,
        email=data.email,
        phone=data.phone,
        tanggal_lahir=data.tanggal_lahir,
        alamat=data.alamat,
        program_studi_id=prodi.id,
        jalur_masuk_id=jalur.id,
        status=StatusPendaftaran.PENDING,
        nim=None,
        created_at=datetime.now(timezone.utc),
        approved_at=None
    )

    db.add(new_calon)
    db.commit()
    db.refresh(new_calon)
    return new_calon


def get_calon_mahasiswa_by_id(calon_id: int, db: Session) -> CalonMahasiswa:
    calon = db.query(CalonMahasiswa).filter(CalonMahasiswa.id == calon_id).first()
    if not calon:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Calon mahasiswa dengan ID {calon_id} tidak ditemukan."
        )
    return calon


def approve_calon_mahasiswa(calon_id: int, db: Session) -> CalonMahasiswa:
    with _nim_lock:
        calon = db.query(CalonMahasiswa).filter(CalonMahasiswa.id == calon_id).first()
        if not calon:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Calon mahasiswa dengan ID {calon_id} tidak ditemukan."
            )

        # Idempotency check: Jika sudah approved dan memiliki NIM, jangan generate ulang
        if calon.status == StatusPendaftaran.APPROVED and calon.nim:
            return calon

        tahun = calon.created_at.year if calon.created_at else datetime.now(timezone.utc).year
        kode_prodi = calon.program_studi.kode if calon.program_studi else "001"

        new_nim = generate_nim(tahun=tahun, kode_prodi=kode_prodi, db=db)

        calon.status = StatusPendaftaran.APPROVED
        calon.nim = new_nim
        calon.approved_at = datetime.now(timezone.utc)

        db.commit()
        db.refresh(calon)
        return calon


def get_pmb_statistics(db: Session) -> Dict[str, Any]:
    total_pendaftar = db.query(CalonMahasiswa).count()

    # Hitung per status
    by_status = {
        StatusPendaftaran.PENDING.value: 0,
        StatusPendaftaran.APPROVED.value: 0,
        StatusPendaftaran.REJECTED.value: 0
    }
    status_counts = (
        db.query(CalonMahasiswa.status, func.count(CalonMahasiswa.id))
        .group_by(CalonMahasiswa.status)
        .all()
    )
    for st, count in status_counts:
        st_val = st.value if hasattr(st, "value") else str(st)
        by_status[st_val] = count

    # Hitung per program studi
    by_program_studi = {}
    prodi_counts = (
        db.query(ProgramStudi.nama, func.count(CalonMahasiswa.id))
        .join(CalonMahasiswa, CalonMahasiswa.program_studi_id == ProgramStudi.id, isouter=True)
        .group_by(ProgramStudi.nama)
        .all()
    )
    for prodi_nama, count in prodi_counts:
        by_program_studi[prodi_nama] = count

    # Hitung per jalur masuk
    by_jalur_masuk = {}
    jalur_counts = (
        db.query(JalurMasuk.kode, func.count(CalonMahasiswa.id))
        .join(CalonMahasiswa, CalonMahasiswa.jalur_masuk_id == JalurMasuk.id, isouter=True)
        .group_by(JalurMasuk.kode)
        .all()
    )
    for jalur_kode, count in jalur_counts:
        by_jalur_masuk[jalur_kode] = count

    return {
        "total_pendaftar": total_pendaftar,
        "by_status": by_status,
        "by_program_studi": by_program_studi,
        "by_jalur_masuk": by_jalur_masuk
    }
