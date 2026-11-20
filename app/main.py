"""Entry point aplikasi FastAPI untuk modul PMB SEVIMA-Mini."""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.routers.pmb import router as pmb_router

app = FastAPI(
    title="SEVIMA-Mini — Modul PMB API",
    description=(
        "REST API Penerimaan Mahasiswa Baru (PMB) dengan validasi input, "
        "state machine approve/reject, dan NIM generator otomatis yang idempotent "
        "serta aman dari race condition."
    ),
    version="1.0.0",
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Mengubah default 422 Pydantic/FastAPI menjadi 400 Bad Request sesuai spesifikasi tugas."""
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": jsonable_encoder(exc.errors())},
    )


@app.get("/health", tags=["System"], summary="Health check layanan")
def health_check() -> dict[str, str]:
    """Memastikan layanan API berjalan normal."""
    return {"status": "ok"}


app.include_router(pmb_router)
