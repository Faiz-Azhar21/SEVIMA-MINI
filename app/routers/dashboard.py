"""Router Deliverable 3: Dashboard Keuangan Real-Time (API + SSE Stream)."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.dashboard_service import get_dashboard_overview
from app.services.realtime import realtime_broker

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard Keuangan"])


@router.get("")
def api_dashboard_overview(
    semester: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Endpoint utama dashboard keuangan real-time."""
    return get_dashboard_overview(db, semester=semester)


@router.get("/stream")
async def api_dashboard_stream(request: Request) -> StreamingResponse:
    """Server-Sent Events (SSE) stream untuk mendorong update real-time ke frontend."""
    queue = realtime_broker.subscribe()

    async def event_generator():
        try:
            yield 'event: connected\ndata: {"status":"connected"}\n\n'
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=20.0)
                    yield f"event: update\ndata: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            realtime_broker.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
