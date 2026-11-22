"""Test Deliverable 4: Payment Webhook Simulation (HMAC Signature, Update Status, Email Receipt)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Billing, EmailLog, Mahasiswa, Payment
from app.services.billing_service import generate_billing
from app.services.webhook_service import generate_signature


def test_webhook_rejects_invalid_or_missing_signature(
    seeded_basic_db: Session, client: TestClient
) -> None:
    generate_billing(seeded_basic_db, semester="2026/2027-Ganjil", semester_start=date(2026, 9, 1))
    billing = (
        seeded_basic_db.execute(select(Billing).join(Mahasiswa).where(Mahasiswa.nim == "2401001")).scalar_one()
    )
    body = json.dumps(
        {
            "transaction_id": "WH-INVALID-1",
            "billing_id": billing.id,
            "amount": 5_000_000,
            "status": "paid",
        }
    )

    resp_missing = client.post("/api/webhook/payment", content=body, headers={"Content-Type": "application/json"})
    assert resp_missing.status_code == 401

    resp_wrong = client.post(
        "/api/webhook/payment",
        content=body,
        headers={"Content-Type": "application/json", "X-Signature": "deadbeef1234"},
    )
    assert resp_wrong.status_code == 401


def test_webhook_valid_payment_updates_billing_sends_receipt_and_is_idempotent(
    seeded_basic_db: Session, client: TestClient
) -> None:
    generate_billing(seeded_basic_db, semester="2026/2027-Ganjil", semester_start=date(2026, 9, 1))
    billing = (
        seeded_basic_db.execute(select(Billing).join(Mahasiswa).where(Mahasiswa.nim == "2401001")).scalar_one()
    )
    assert billing.status == "unpaid"

    raw_body = json.dumps(
        {
            "transaction_id": "GW-20261123-0001",
            "billing_id": billing.id,
            "amount": 5_000_000,
            "status": "paid",
            "payment_method": "VA_BCA",
        },
        separators=(",", ":"),
    )
    sig = generate_signature(raw_body)

    # 1. Kirim webhook valid -> 200 OK, unpaid -> paid, receipt terkirim
    resp = client.post(
        "/api/webhook/payment",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Signature": sig},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "processed"
    assert data["previous_status"] == "unpaid"
    assert data["new_status"] == "paid"
    assert data["receipt_sent"] is True
    assert data["receipt"]["recipient"] == "andi@kampus.ac.id"
    assert Path(data["receipt"]["receipt_file"]).exists()

    # Verifikasi DB
    seeded_basic_db.refresh(billing)
    assert billing.status == "paid"
    assert billing.paid_amount == 5_000_000
    email_logs = seeded_basic_db.execute(select(EmailLog).where(EmailLog.email_type == "receipt")).scalars().all()
    assert len(email_logs) == 1

    # 2. Simulasi retry webhook yang sama -> idempotent, tidak double-charge & tidak kirim receipt ganda
    resp_retry = client.post(
        "/api/webhook/payment",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Signature": sig},
    )
    assert resp_retry.status_code == 200
    assert resp_retry.json()["status"] == "duplicate_ignored"
    assert resp_retry.json()["receipt_sent"] is False

    payments = seeded_basic_db.execute(select(Payment).where(Payment.billing_id == billing.id)).scalars().all()
    assert len(payments) == 1


def test_webhook_ignores_non_success_status(seeded_basic_db: Session, client: TestClient) -> None:
    generate_billing(seeded_basic_db, semester="2026/2027-Ganjil", semester_start=date(2026, 9, 1))
    billing = (
        seeded_basic_db.execute(select(Billing).join(Mahasiswa).where(Mahasiswa.nim == "2402001")).scalar_one()
    )

    raw_body = json.dumps(
        {
            "transaction_id": "GW-FAILED-01",
            "billing_id": billing.id,
            "amount": 4_000_000,
            "status": "failed",
        }
    )
    sig = generate_signature(raw_body)
    resp = client.post(
        "/api/webhook/payment",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Signature": sig},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"
    seeded_basic_db.refresh(billing)
    assert billing.status == "unpaid"
