"""Entry point FastAPI aplikasi SEVIMA-Mini."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.routers.jadwal import router as jadwal_router
from app.services.exceptions import ScheduleError

app = FastAPI(
    title="SEVIMA-Mini — Modul Jadwal & Ruangan",
    version="0.7.0",
    description="Materi 4 Minggu 7: CSP Hard Constraints, Deteksi Bentrok 3D, dan Scheduling Service.",
)


@app.exception_handler(ScheduleError)
async def schedule_error_handler(
    _request: Request, exc: ScheduleError
) -> JSONResponse:
    """Satu handler polimorfik untuk seluruh turunan ScheduleError."""
    return JSONResponse(status_code=exc.status_code, content=exc.body())


app.include_router(jadwal_router)
