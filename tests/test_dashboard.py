"""Test Deliverable 3: Dashboard Keuangan Real-Time."""

from __future__ import annotations

import json
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Billing, Mahasiswa
from app.services.billing_service import generate_billing
from app.services.webhook_service import generate_signature


def test_dashboard_html_and_realtime_update_after_webhook(
    seeded_basic_db: Session, client: TestClient
) -> None:
    # 1. Frontend HTML tersedia
    html_resp = client.get("/")
    assert html_resp.status_code == 200
    assert "Dashboard Keuangan SPP" in html_resp.text

    # 2. Generate billing -> cek metrik sebelum bayar
    generate_billing(seeded_basic_db, semester="2026/2027-Ganjil", semester_start=date(2026, 9, 1))
    before = client.get("/api/dashboard").json()
    assert before["summary"]["total_tagihan"] == 9_000_000
    assert before["summary"]["total_terbayar"] == 0
    assert before["summary"]["total_sisa"] == 9_000_000
    assert before["summary"]["collection_rate_students"] == 0.0
    assert before["summary"]["mahasiswa_diblokir_krs"] == 2

    # 3. Bayar mahasiswa Teknik (Rp 5 jt) via webhook -> dashboard langsung real-time update
    teknik_bill = (
        seeded_basic_db.execute(select(Billing).join(Mahasiswa).where(Mahasiswa.nim == "2401001")).scalar_one()
    )
    raw = json.dumps(
        {
            "transaction_id": "DASH-WH-1",
            "billing_id": teknik_bill.id,
            "amount": 5_000_000,
            "status": "paid",
        }
    )
    wh_resp = client.post(
        "/api/webhook/payment",
        content=raw,
        headers={"Content-Type": "application/json", "X-Signature": generate_signature(raw)},
    )
    assert wh_resp.status_code == 200

    after = client.get("/api/dashboard").json()
    assert after["summary"]["total_terbayar"] == 5_000_000
    assert after["summary"]["total_sisa"] == 4_000_000
    assert after["summary"]["collection_rate_students"] == 50.0
    assert after["summary"]["mahasiswa_diblokir_krs"] == 1

    # Cek collection rate per prodi: Teknik 100%, Ekonomi 0%
    prodi_by_name = {p["program_studi"]: p for p in after["per_program_studi"]}
    assert prodi_by_name["Teknik"]["collection_rate_students"] == 100.0
    assert prodi_by_name["Ekonomi"]["collection_rate_students"] == 0.0

    # Grafik pembayaran per bulan memiliki minimal 1 entri
    assert len(after["monthly_chart"]) == 1
    assert after["monthly_chart"][0]["total_amount"] == 5_000_000
