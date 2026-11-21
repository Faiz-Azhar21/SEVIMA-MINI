"""Entrypoint FastAPI untuk SEVIMA-Mini Modul Nilai & Transkrip (Minggu 9)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.database import Base, SessionLocal, engine
from app.routers.nilai import kelas_router, mahasiswa_router, referensi_router
from app.routers.web import web_router
from app.seed import seed_dummy_data
from app.services.grade_service import GradeError


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Inisialisasi tabel, view riwayat, dan data dummy saat aplikasi dijalankan."""
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_dummy_data(db)
    yield


def create_app(init_db_on_startup: bool = True) -> FastAPI:
    """Factory FastAPI app (memudahkan isolasi test tanpa menyentuh DB produksi)."""
    app = FastAPI(
        title="SEVIMA-Mini — Modul Nilai & Transkrip (Minggu 9)",
        version="0.9.0",
        lifespan=lifespan if init_db_on_startup else None,
    )

    @app.exception_handler(GradeError)
    async def grade_error_handler(_request: Request, exc: GradeError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})

    app.include_router(kelas_router)
    app.include_router(mahasiswa_router)
    app.include_router(referensi_router)
    app.include_router(web_router)
    return app


app = create_app()
