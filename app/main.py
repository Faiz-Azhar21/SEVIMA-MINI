"""Entrypoint FastAPI untuk Modul Keuangan (SPP) - Minggu 11."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import database
from app.config import ENABLE_SCHEDULER
from app.routers import ai_report, billing, dashboard, krs, webhook
from app.seed import seed_database
from app.services.scheduler_service import scheduler_manager

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    database.init_db()
    db = database.SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()

    if ENABLE_SCHEDULER:
        scheduler_manager.start()

    try:
        yield
    finally:
        scheduler_manager.shutdown()


app = FastAPI(
    title="Sistem Manajemen Pembayaran SPP (Modul Keuangan)",
    description=(
        "Minggu 11: Payment State Management, Scheduled Jobs (APScheduler), "
        "Payment Webhook Simulation (HMAC-SHA256 + Email Receipt), Block KRS, "
        "Dashboard Keuangan Real-Time, dan AI Financial Report."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(billing.router)
app.include_router(webhook.router)
app.include_router(krs.router)
app.include_router(dashboard.router)
app.include_router(ai_report.router)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
def serve_dashboard() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health", tags=["System"])
def health_check() -> dict[str, str]:
    return {"status": "ok", "module": "Modul Keuangan SPP - Minggu 11"}
