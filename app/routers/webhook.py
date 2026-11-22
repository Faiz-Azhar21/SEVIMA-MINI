"""Router Deliverable 4: Payment Webhook Simulation."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import WebhookSignPreviewRequest
from app.services.webhook_service import (
    WebhookSignatureError,
    generate_signature,
    handle_webhook,
)

router = APIRouter(prefix="/api/webhook", tags=["Payment Webhook"])


@router.post("/payment")
async def receive_payment_webhook(
    request: Request,
    x_signature: str | None = Header(default=None, alias="X-Signature"),
    x_webhook_signature: str | None = Header(default=None, alias="X-Webhook-Signature"),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Endpoint menerima notifikasi pembayaran dari Payment Gateway (simulasi).

    Header keamanan: `X-Signature: <hex HMAC-SHA256 dari raw request body>`.
    """
    raw_body = await request.body()
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Payload JSON tidak valid.") from exc

    signature = x_signature or x_webhook_signature
    try:
        return handle_webhook(db=db, payload=payload, raw_body=raw_body, signature=signature)
    except WebhookSignatureError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/sign-preview")
def preview_webhook_signature(payload: WebhookSignPreviewRequest) -> dict[str, Any]:
    """Helper simulasi gateway: menghasilkan raw JSON, HMAC-SHA256 signature, dan perintah curl."""
    raw_json = json.dumps(payload.model_dump(), separators=(",", ":"))
    sig = generate_signature(raw_json)
    curl_cmd = (
        f'curl -X POST http://127.0.0.1:8000/api/webhook/payment '
        f'-H "Content-Type: application/json" '
        f'-H "X-Signature: {sig}" '
        f"-d '{raw_json}'"
    )
    return {
        "raw_payload": raw_json,
        "signature": sig,
        "curl_command": curl_cmd,
    }
