"""Entrypoint FastAPI untuk Modul Presensi Berbasis QR Code (Tugas Minggu 12)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.database import SessionLocal, init_db
from app.routers.attendance import router as attendance_router
from app.seed import seed_database

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title="Sistem Presensi QR Code & AI Attendance Insights",
    description=(
        "Tugas Minggu 12: Modul Presensi berbasis QR Code dengan validasi JWT 15 menit, "
        "anti-replay token, validasi jadwal & enrollment, geolocation opsional, rate limiting, "
        "laporan & export Excel, serta AI Attendance Analyzer."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(attendance_router)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", include_in_schema=False)
def serve_dashboard():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "Sistem Presensi QR Code berjalan. Buka /docs untuk API Swagger."}


@app.get("/health", tags=["System"])
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "modul-presensi-qr-minggu-12"}
