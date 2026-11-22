"""Deliverable 4: Payment Webhook Simulation (15%).

Menangani:
- Verifikasi signature HMAC-SHA256 (keamanan webhook)
- Ekstraksi payload (transaction_id, billing_id/billing_code, amount, status)
- Pemanggilan `process_payment` secara atomik
- Pengiriman email kuitansi (receipt) setelah transaksi commit
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.config import WEBHOOK_SECRET
from app.models import Billing, PaymentMethod, PaymentSource
from app.services.billing_service import process_payment
from app.services.email_service import format_rupiah, send_payment_receipt


class WebhookSignatureError(Exception):
    """Dilempar ketika signature webhook tidak valid atau tidak ditemukan."""


SUCCESS_GATEWAY_STATUSES = {"paid", "settlement", "success", "captured"}


def generate_signature(raw_body: bytes | str, secret: str | None = None) -> str:
    """Menghasilkan hex digest HMAC-SHA256 untuk payload webhook."""
    key = (secret if secret is not None else WEBHOOK_SECRET).encode("utf-8")
    body_bytes = raw_body.encode("utf-8") if isinstance(raw_body, str) else raw_body
    return hmac.new(key, body_bytes, hashlib.sha256).hexdigest()


def verify_signature(raw_body: bytes | str, signature: str | None, secret: str | None = None) -> bool:
    """Memverifikasi signature webhook secara timing-safe (tahan timing attack)."""
    if not signature:
        return False
    provided = signature.strip()
    if provided.lower().startswith("sha256="):
        provided = provided[7:]
    expected = generate_signature(raw_body, secret=secret)
    return hmac.compare_digest(expected.lower(), provided.lower())


def handle_webhook(
    db: Session,
    payload: dict[str, Any],
    *,
    raw_body: bytes | str | None = None,
    signature: str | None = None,
    secret: str | None = None,
) -> dict[str, Any]:
    """Step 2.2: Handler utama webhook konfirmasi pembayaran dari gateway.

    Alur:
    1. Verify signature (HMAC-SHA256)
    2. Extract: transaction_id, billing_id/billing_code, amount, status, payment_method
    3. Jika status sukses -> panggil `process_payment` (DB transaction atomik)
    4. Kirim email receipt (bukan duplikat)
    5. Return payload 200 OK
    """
    body_for_verify = (
        raw_body
        if raw_body is not None
        else json.dumps(payload, separators=(",", ":"), sort_keys=True)
    )
    if not verify_signature(body_for_verify, signature, secret=secret):
        raise WebhookSignatureError("Signature webhook tidak valid atau tidak disertakan.")

    transaction_id = str(payload.get("transaction_id", "")).strip()
    gateway_status = str(payload.get("status", "")).strip().lower()
    amount = payload.get("amount")
    billing_id = payload.get("billing_id")
    billing_code = payload.get("billing_code")
    payment_method = payload.get("payment_method") or "VA_BCA"

    if not transaction_id:
        raise ValueError("Payload webhook harus menyertakan 'transaction_id'.")
    if amount is None or int(amount) <= 0:
        raise ValueError("Payload webhook harus menyertakan 'amount' > 0.")

    # Resolve billing_id melalui billing_code jika billing_id tidak langsung dikirim
    if billing_id is None and billing_code:
        found_billing = db.execute(
            select(Billing).where(Billing.billing_code == billing_code)
        ).scalar_one_or_none()
        if found_billing is None:
            raise LookupError(f"Billing dengan kode '{billing_code}' tidak ditemukan.")
        billing_id = found_billing.id

    if billing_id is None:
        raise ValueError("Payload webhook harus menyertakan 'billing_id' atau 'billing_code'.")

    # Jika status dari gateway bukan sukses (misal pending/failed), terima 200 OK tanpa mengubah billing jadi paid
    if gateway_status not in SUCCESS_GATEWAY_STATUSES:
        return {
            "status": "ignored",
            "http_status": 200,
            "message": f"Notifikasi webhook diterima dengan status gateway '{gateway_status}' (belum diproses sebagai lunas).",
            "transaction_id": transaction_id,
            "billing_id": int(billing_id),
            "receipt_sent": False,
        }

    paid_at_raw = payload.get("paid_at")
    paid_at: datetime | None = None
    if isinstance(paid_at_raw, datetime):
        paid_at = paid_at_raw
    elif isinstance(paid_at_raw, str) and paid_at_raw.strip():
        paid_at = datetime.fromisoformat(paid_at_raw.replace("Z", "+00:00")).replace(tzinfo=None)

    raw_json_str = (
        raw_body.decode("utf-8", errors="replace")
        if isinstance(raw_body, bytes)
        else (raw_body if isinstance(raw_body, str) else json.dumps(payload, default=str))
    )

    result = process_payment(
        db=db,
        billing_id=int(billing_id),
        amount=int(amount),
        method=payment_method,
        transaction_id=transaction_id,
        source=PaymentSource.WEBHOOK.value,
        paid_at=paid_at,
        notes=f"Konfirmasi otomatis via Payment Gateway Webhook (status={gateway_status})",
        raw_payload=raw_json_str,
    )

    receipt_info: dict[str, Any] | None = None
    if not result.duplicate:
        billing_with_mhs = db.execute(
            select(Billing)
            .options(joinedload(Billing.mahasiswa))
            .where(Billing.id == result.billing.id)
        ).scalar_one()
        pm = db.get(PaymentMethod, result.payment.payment_method_id)
        pm_name = pm.name if pm else str(payment_method)

        email_log = send_payment_receipt(
            db=db,
            mahasiswa=billing_with_mhs.mahasiswa,
            billing=billing_with_mhs,
            payment=result.payment,
            payment_method_name=pm_name,
        )
        receipt_info = {
            "email_log_id": email_log.id,
            "recipient": email_log.recipient_email,
            "delivery_status": email_log.delivery_status,
            "receipt_file": email_log.receipt_file_path,
        }

    return {
        "status": "duplicate_ignored" if result.duplicate else "processed",
        "http_status": 200,
        "message": (
            f"Transaksi {transaction_id} sudah pernah diproses sebelumnya (idempotent)."
            if result.duplicate
            else f"Pembayaran {format_rupiah(result.payment.amount)} berhasil dikonfirmasi via webhook."
        ),
        "transaction_id": result.payment.transaction_id,
        "billing_id": result.billing.id,
        "billing_code": result.billing.billing_code,
        "previous_status": result.previous_status,
        "new_status": result.new_status,
        "paid_amount": result.billing.paid_amount,
        "total_amount": result.billing.total_amount,
        "remaining_amount": result.billing.remaining_amount,
        "receipt_sent": receipt_info is not None,
        "receipt": receipt_info,
    }
