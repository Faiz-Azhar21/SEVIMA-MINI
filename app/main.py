"""Entry point FastAPI SEVIMA-Mini (Modul KRS — Minggu 5)."""

from fastapi import FastAPI

from app.api.krs import router as krs_router

app = FastAPI(
    title="SEVIMA-Mini API — Modul KRS",
    description=(
        "Implementasi Modul KRS (Kartu Rencana Studi) Minggu 5: "
        "Skema KRS, KRSManager Service, Chain of Responsibility Validator, "
        "dan Query Prasyarat NOT EXISTS."
    ),
    version="0.5.0",
)

app.include_router(krs_router)


@app.get("/health", tags=["System"])
def health_check() -> dict[str, str]:
    """Endpoint pengecekan kesehatan layanan."""
    return {"status": "ok"}
