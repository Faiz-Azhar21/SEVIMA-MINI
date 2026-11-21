"""API Router untuk Modul Jadwal & Ruangan (/api/jadwal)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.jadwal import ConflictOut, JadwalIn, JadwalOut
from app.services.scheduling import SchedulingService

router = APIRouter(prefix="/api/jadwal", tags=["jadwal"])


@router.get("", response_model=list[JadwalOut])
def daftar_jadwal(db: Session = Depends(get_db)) -> list[JadwalOut]:
    """Daftar seluruh jadwal kuliah."""
    return [JadwalOut.model_validate(j) for j in SchedulingService(db).list_all()]


@router.post("", status_code=201, response_model=JadwalOut)
def buat_jadwal(data: JadwalIn, db: Session = Depends(get_db)) -> JadwalOut:
    """Buat jadwal kuliah baru (tolak bentrok & kapasitas berlebih dengan HTTP 409)."""
    jadwal = SchedulingService(db).create(data)
    return JadwalOut.model_validate(jadwal)


@router.get("/conflicts", response_model=list[ConflictOut])
def daftar_konflik(db: Session = Depends(get_db)) -> list[ConflictOut]:
    """Laporkan seluruh bentrok ruangan/dosen di database (sumber data dashboard admin)."""
    return [
        ConflictOut(type=k.type, affected=list(k.affected))
        for k in SchedulingService(db).list_conflicts()
    ]


@router.put("/{jadwal_id}", response_model=JadwalOut)
def ubah_jadwal(
    jadwal_id: int, data: JadwalIn, db: Session = Depends(get_db)
) -> JadwalOut:
    """Perbarui jadwal kuliah yang sudah ada."""
    jadwal = SchedulingService(db).update(jadwal_id, data)
    return JadwalOut.model_validate(jadwal)


@router.delete("/{jadwal_id}", status_code=204)
def hapus_jadwal(jadwal_id: int, db: Session = Depends(get_db)) -> Response:
    """Hapus jadwal kuliah."""
    SchedulingService(db).delete(jadwal_id)
    return Response(status_code=204)
