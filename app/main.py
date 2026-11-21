"""Entry point FastAPI SEVIMA-Mini — Modul Jadwal & Ruangan (Minggu 7-8).

Merangkai Observer (StudentObserver, LecturerObserver, AdminObserver) dan 3 kanal
(EMAIL, SMS, PUSH) SEKALI saat startup (lifespan), bukan di dalam endpoint,
untuk menghindari memory leak & notifikasi berlipat.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.database import SessionLocal, init_db
from app.scheduling.observer import (
    AdminObserver,
    InMemoryIdemStore,
    LecturerObserver,
    LogChannel,
    ScheduleSubject,
    StudentObserver,
)
from app.scheduling.repos import SqlDosenRepo, SqlPesertaRepo
from app.scheduling.router import (
    admin_monitor_router,
    calendar_router,
    jadwal_router,
    runtime_state,
)
from app.seed import seed_demo_data

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)

STATIC_DIR = Path(__file__).resolve().parent / "static"


def wire_observers(
    session_factory=SessionLocal,
    log_sink: list | None = None,
) -> tuple[ScheduleSubject, InMemoryIdemStore]:
    """Merangkai ScheduleSubject + 3 observer + 3 kanal (EMAIL, SMS, PUSH) sekali saat startup."""
    store = InMemoryIdemStore()
    sink = log_sink if log_sink is not None else runtime_state.notification_logs
    channels = [
        LogChannel(nama, store=store, log_sink=sink)
        for nama in ("EMAIL", "SMS", "PUSH")
    ]
    subject = ScheduleSubject()
    subject.attach(StudentObserver(SqlPesertaRepo(session_factory), channels))
    subject.attach(LecturerObserver(SqlDosenRepo(session_factory), channels))
    subject.attach(AdminObserver(channels))
    return subject, store


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        seed_demo_data(db)
    finally:
        db.close()

    # Rangkai observer SEKALI saat startup (bukan per-request!)
    subject, _ = wire_observers(SessionLocal, runtime_state.notification_logs)
    runtime_state.subject = subject
    yield


app = FastAPI(
    title="SEVIMA-Mini — Modul Jadwal & Ruangan (Minggu 7-8)",
    description=(
        "Sistem penjadwalan kuliah dengan deteksi bentrok 3 dimensi (Interval Tree), "
        "Observer Pattern + Transactional Outbox + Idempotency Key, Integrasi KRS, "
        "AI-Powered Rescheduling (4 saringan), Conflict Resolver UI, dan ekspor .ics."
    ),
    version="0.8.0",
    lifespan=lifespan,
)

app.include_router(jadwal_router)
app.include_router(admin_monitor_router)
app.include_router(calendar_router)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
def serve_dashboard() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
