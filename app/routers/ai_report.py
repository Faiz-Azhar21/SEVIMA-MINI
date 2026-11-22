"""Router Deliverable 5: AI Financial Report (CSV -> JSON Insights)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Mahasiswa
from app.services.ai_report_service import (
    analyze_payment_csv,
    export_live_payment_csv,
    generate_ai_report_from_db,
    generate_ai_report_from_file,
)

router = APIRouter(prefix="/api/ai-report", tags=["AI Financial Report"])


@router.get("")
def api_get_ai_report(
    source: str = Query(default="live", pattern="^(live|sample_csv)$"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Menghasilkan AI Financial Report dalam format JSON untuk dashboard frontend."""
    if source == "sample_csv":
        try:
            return generate_ai_report_from_file(db=db)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="File data/payment_data.csv tidak ditemukan.") from exc
    return generate_ai_report_from_db(db)


@router.post("/analyze-csv")
async def api_analyze_uploaded_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Upload file CSV (kolom: nim, jumlah, tanggal, status) untuk dianalisis menjadi JSON insight."""
    raw = await file.read()
    try:
        csv_text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="File CSV harus ber-encoding UTF-8.") from exc

    students = db.execute(select(Mahasiswa)).scalars().all()
    lookup = {m.nim: {"nama": m.nama, "program_studi": m.program_studi} for m in students}

    try:
        report = analyze_payment_csv(csv_text, student_lookup=lookup)
        report["data_source"] = file.filename or "uploaded.csv"
        return report
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/export-csv")
def api_export_payment_csv(db: Session = Depends(get_db)) -> PlainTextResponse:
    """Mengekspor data pembayaran live ke format CSV (nim, jumlah, tanggal, status)."""
    csv_text = export_live_payment_csv(db)
    return PlainTextResponse(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="payment_data.csv"'},
    )
