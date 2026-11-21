"""Router halaman web sederhana untuk form input & edit nilai oleh dosen."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
web_router = APIRouter(tags=["web"])


@web_router.get("/", response_class=HTMLResponse)
@web_router.get("/nilai", response_class=HTMLResponse)
def form_input_nilai() -> HTMLResponse:
    """Sajikan halaman form input nilai dosen (tanpa dependensi template engine eksternal)."""
    html = (STATIC_DIR / "nilai_form.html").read_text(encoding="utf-8")
    return HTMLResponse(content=html)
