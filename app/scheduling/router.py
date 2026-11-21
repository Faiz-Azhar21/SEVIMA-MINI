"""FastAPI Router untuk Modul Jadwal & Ruangan, Conflict Resolver, KRS, Log, dan .ics."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.auth import require_admin
from app.database import get_db
from app.krs.invalidator import KRSInvalidator
from app.krs.models import KRS
from app.scheduling.ai_rescheduler import LLMClient, get_default_llm_client
from app.scheduling.conflict import (
    CapacityExceededError,
    ScheduleConflictError,
    hitung_peserta_kelas,
)
from app.scheduling.models import Jadwal, Kelas, Outbox
from app.scheduling.observer import ScheduleSubject
from app.scheduling.outbox import OutboxDispatcher
from app.scheduling.schemas import ConflictOut, JadwalIn, JadwalOut, KRSOut, OutboxOut, Saran
from app.scheduling.service import NotFoundError, SchedulingService, snapshot


class AppRuntimeState:
    """State bersama yang dirangkai SEKALI saat aplikasi start (mencegah memory leak attach)."""

    def __init__(self) -> None:
        self.subject: ScheduleSubject = ScheduleSubject()
        self.notification_logs: list[dict[str, Any]] = []
        self.llm_client: LLMClient = get_default_llm_client()


runtime_state = AppRuntimeState()


def get_llm() -> LLMClient:
    return runtime_state.llm_client


def get_service(db: Session = Depends(get_db)) -> SchedulingService:
    dispatcher = OutboxDispatcher(db=db, subject=runtime_state.subject)
    return SchedulingService(db=db, krs=KRSInvalidator(db), dispatcher=dispatcher)


def _to_jadwal_out(db: Session, j: Jadwal) -> JadwalOut:
    _, terdaftar = hitung_peserta_kelas(db, j.kelas_id)
    return JadwalOut(
        id=j.id,
        kelas_id=j.kelas_id,
        nama_kelas=j.kelas.nama if j.kelas else f"Kelas #{j.kelas_id}",
        hari=j.hari,
        jam_mulai=j.jam_mulai,
        jam_selesai=j.jam_selesai,
        ruangan_kode=j.ruangan_kode,
        kapasitas_ruangan=j.ruangan.kapasitas if j.ruangan else 0,
        dosen_id=j.dosen_id,
        nama_dosen=j.dosen.nama if j.dosen else f"Dosen #{j.dosen_id}",
        kuota_kelas=j.kelas.kuota if j.kelas else 0,
        terdaftar=terdaftar,
        sequence=j.sequence,
    )


# Router khusus Admin Akademik (semua endpoint jadwal dilindungi require_admin)
jadwal_router = APIRouter(
    prefix="/api/jadwal",
    tags=["Jadwal & Conflict Resolver"],
    dependencies=[Depends(require_admin)],
)


@jadwal_router.get("", response_model=list[JadwalOut])
def list_jadwal(
    svc: SchedulingService = Depends(get_service),
    db: Session = Depends(get_db),
) -> list[JadwalOut]:
    return [_to_jadwal_out(db, j) for j in svc.list_jadwal()]


@jadwal_router.get("/conflicts", response_model=list[ConflictOut])
def list_conflicts(
    svc: SchedulingService = Depends(get_service),
) -> list[ConflictOut]:
    semua = {j.id: j for j in svc.list_jadwal()}
    conflicts = svc.detect_all_conflicts()
    hasil: list[ConflictOut] = []
    for c in conflicts:
        scheds = [
            snapshot(semua[jid]) for jid in c.affected if jid in semua
        ]
        hasil.append(
            ConflictOut(
                type=c.type,
                affected=c.affected,
                detail=c.detail,
                schedules=scheds,
            )
        )
    return hasil


@jadwal_router.post("", response_model=JadwalOut, status_code=status.HTTP_201_CREATED)
def create_jadwal(
    data: JadwalIn,
    svc: SchedulingService = Depends(get_service),
    db: Session = Depends(get_db),
) -> JadwalOut:
    try:
        j = svc.create(data)
        return _to_jadwal_out(db, svc.get_jadwal(j.id))
    except (ScheduleConflictError, CapacityExceededError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@jadwal_router.put("/{jadwal_id}", response_model=JadwalOut)
def update_jadwal(
    jadwal_id: int,
    data: JadwalIn,
    svc: SchedulingService = Depends(get_service),
    db: Session = Depends(get_db),
) -> JadwalOut:
    try:
        j = svc.update(jadwal_id, data)
        return _to_jadwal_out(db, svc.get_jadwal(j.id))
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (ScheduleConflictError, CapacityExceededError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@jadwal_router.delete("/{jadwal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_jadwal(
    jadwal_id: int,
    svc: SchedulingService = Depends(get_service),
) -> Response:
    try:
        svc.delete(jadwal_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@jadwal_router.get("/{jadwal_id}/suggestions", response_model=list[Saran])
def saran_alternatif(
    jadwal_id: int,
    svc: SchedulingService = Depends(get_service),
    llm: LLMClient = Depends(get_llm),
) -> list[Saran]:
    try:
        return svc.cari_alternatif(jadwal_id, llm)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@jadwal_router.post("/{jadwal_id}/apply", response_model=JadwalOut)
def terapkan_saran(
    jadwal_id: int,
    saran: Saran,
    svc: SchedulingService = Depends(get_service),
    db: Session = Depends(get_db),
) -> JadwalOut:
    """Tombol Terapkan di Conflict Resolver: melewati ``SchedulingService.update()`` (satu pintu)."""
    try:
        j = svc.apply_saran(jadwal_id, saran)
        return _to_jadwal_out(db, svc.get_jadwal(j.id))
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (ScheduleConflictError, CapacityExceededError) as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"{exc}. Muat ulang saran alternatif.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# Router untuk monitoring Admin (KRS, Outbox, Log Notifikasi)
admin_monitor_router = APIRouter(
    prefix="/api",
    tags=["Monitoring & Audit"],
    dependencies=[Depends(require_admin)],
)


@admin_monitor_router.get("/krs", response_model=list[KRSOut])
def list_krs(db: Session = Depends(get_db)) -> list[KRSOut]:
    kelas_map = {k.id: k.nama for k in db.scalars(select(Kelas))}
    stmt = select(KRS).options(joinedload(KRS.mahasiswa), joinedload(KRS.details)).order_by(KRS.id)
    hasil: list[KRSOut] = []
    for krs in db.scalars(stmt).unique():
        kelas_ids = [d.kelas_id for d in krs.details]
        hasil.append(
            KRSOut(
                id=krs.id,
                nim=krs.nim,
                nama_mahasiswa=krs.mahasiswa.nama if krs.mahasiswa else krs.nim,
                semester=krs.semester,
                status=krs.status.value,
                catatan_revisi=krs.catatan_revisi,
                kelas_ids=kelas_ids,
                mata_kuliah=[kelas_map.get(kid, f"Kelas #{kid}") for kid in kelas_ids],
            )
        )
    return hasil


@admin_monitor_router.get("/outbox", response_model=list[OutboxOut])
def list_outbox(db: Session = Depends(get_db)) -> list[OutboxOut]:
    rows = list(db.scalars(select(Outbox).order_by(Outbox.id.desc()).limit(50)))
    return [OutboxOut.model_validate(r) for r in rows]


@admin_monitor_router.get("/logs/notifications")
def list_notification_logs() -> list[dict[str, Any]]:
    return list(reversed(runtime_state.notification_logs[-100:]))


# Router publik/mahasiswa untuk ekspor kalender .ics
calendar_router = APIRouter(prefix="/api/mahasiswa", tags=["Calendar (.ics)"])


@calendar_router.get("/{nim}/jadwal.ics")
def download_jadwal_ics(
    nim: str,
    awal: date = date(2026, 9, 7),
    akhir: date = date(2026, 12, 18),
    svc: SchedulingService = Depends(get_service),
) -> Response:
    try:
        content = svc.export_mahasiswa_ics(nim, awal=awal, akhir=akhir)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(
        content=content,
        media_type="text/calendar",
        headers={
            "Content-Disposition": f'attachment; filename="jadwal-{nim}.ics"'
        },
    )
