"""Test Deliverable 2: Billing Service (Generate, Payment Atomicity, Late Fee, Block KRS)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Billing, BillingStatus, Mahasiswa, Payment
from app.services.billing_service import (
    KrsBlockedError,
    apply_overdue_and_penalties,
    calculate_late_fee,
    check_krs_eligibility,
    generate_billing,
    process_payment,
    submit_krs,
)


def test_generate_billing_active_students_tariffs_and_idempotency(seeded_basic_db: Session) -> None:
    sem_start = date(2026, 9, 1)
    res1 = generate_billing(seeded_basic_db, semester="2026/2027-Ganjil", semester_start=sem_start)

    # Hanya 2 mahasiswa aktif (Teknik & Ekonomi); 1 mahasiswa cuti harus dilewati
    assert res1["created_count"] == 2
    assert res1["skipped_existing_count"] == 0
    assert res1["due_date"] == (sem_start + timedelta(days=14)).isoformat()

    billings = seeded_basic_db.execute(select(Billing).join(Mahasiswa).order_by(Mahasiswa.nim)).scalars().all()
    assert len(billings) == 2

    teknik_bill, ekonomi_bill = billings[0], billings[1]
    assert teknik_bill.base_amount == 5_000_000
    assert teknik_bill.total == 5_000_000
    assert teknik_bill.due_date == date(2026, 9, 15)
    assert teknik_bill.status == BillingStatus.UNPAID.value

    assert ekonomi_bill.base_amount == 4_000_000
    assert ekonomi_bill.total == 4_000_000
    assert ekonomi_bill.status == BillingStatus.UNPAID.value

    # Panggilan kedua harus idempoten (0 tagihan baru)
    res2 = generate_billing(seeded_basic_db, semester="2026/2027-Ganjil", semester_start=sem_start)
    assert res2["created_count"] == 0
    assert res2["skipped_existing_count"] == 2


def test_process_payment_partial_then_paid_and_atomicity(
    seeded_basic_db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    generate_billing(seeded_basic_db, semester="2026/2027-Ganjil", semester_start=date(2026, 9, 1))
    billing = (
        seeded_basic_db.execute(select(Billing).join(Mahasiswa).where(Mahasiswa.nim == "2401001")).scalar_one()
    )

    # Cicilan 1: Rp 2.000.000 (< Rp 5.000.000) -> status 'partial'
    r1 = process_payment(
        seeded_basic_db,
        billing_id=billing.id,
        amount=2_000_000,
        method="TRANSFER_MANUAL",
        transaction_id="TX-PART-1",
    )
    assert r1.previous_status == "unpaid"
    assert r1.new_status == "partial"
    assert r1.billing.paid_amount == 2_000_000
    assert r1.billing.remaining_amount == 3_000_000

    # Uji atomicity: simulasikan kegagalan di tengah DB transaction -> rollback penuh
    original_flush = seeded_basic_db.flush

    def _boom_flush(*args, **kwargs):
        raise RuntimeError("Simulated DB crash during commit")

    monkeypatch.setattr(seeded_basic_db, "flush", _boom_flush)
    with pytest.raises(RuntimeError, match="Simulated DB crash"):
        process_payment(
            seeded_basic_db,
            billing_id=billing.id,
            amount=3_000_000,
            method="TRANSFER_MANUAL",
            transaction_id="TX-CRASH-2",
        )
    monkeypatch.setattr(seeded_basic_db, "flush", original_flush)

    # Pastikan rollback terjadi: tidak ada payment TX-CRASH-2 dan paid_amount tetap Rp 2.000.000
    assert (
        seeded_basic_db.execute(select(Payment).where(Payment.transaction_id == "TX-CRASH-2")).scalar_one_or_none()
        is None
    )
    seeded_basic_db.refresh(billing)
    assert billing.paid_amount == 2_000_000
    assert billing.status == "partial"

    # Cicilan 2: Rp 3.000.000 -> total terbayar Rp 5.000.000 >= billing.total -> status 'paid'
    r2 = process_payment(
        seeded_basic_db,
        billing_id=billing.id,
        amount=3_000_000,
        method="VA_BCA",
        transaction_id="TX-PART-2",
    )
    assert r2.previous_status == "partial"
    assert r2.new_status == "paid"
    assert r2.billing.paid_amount == 5_000_000
    assert r2.billing.remaining_amount == 0


def test_late_fee_calculation_and_overdue_application(seeded_basic_db: Session) -> None:
    due = date(2026, 9, 15)

    # Sebelum jatuh tempo -> denda 0
    before = calculate_late_fee(5_000_000, due, as_of_date=date(2026, 9, 15))
    assert before["penalty_amount"] == 0
    assert before["is_overdue"] is False

    # Telat 10 hari -> 10 * 0.5% * 5jt = Rp 250.000
    late_10 = calculate_late_fee(5_000_000, due, as_of_date=date(2026, 9, 25))
    assert late_10["days_late"] == 10
    assert late_10["penalty_amount"] == 250_000

    # Telat 40 hari -> kena cap maksimal 10% = Rp 500.000
    late_40 = calculate_late_fee(5_000_000, due, as_of_date=date(2026, 10, 25))
    assert late_40["penalty_amount"] == 500_000

    # Terapkan ke DB
    generate_billing(seeded_basic_db, semester="2026/2027-Ganjil", semester_start=date(2026, 9, 1))
    summary = apply_overdue_and_penalties(seeded_basic_db, as_of_date=date(2026, 9, 25), send_reminders=True)
    assert summary["overdue_updated"] == 2
    assert summary["reminders_sent"] == 2

    teknik_bill = (
        seeded_basic_db.execute(select(Billing).join(Mahasiswa).where(Mahasiswa.nim == "2401001")).scalar_one()
    )
    assert teknik_bill.status == BillingStatus.OVERDUE.value
    assert teknik_bill.penalty_amount == 250_000
    assert teknik_bill.total_amount == 5_250_000


def test_block_krs_when_unpaid_and_allow_after_paid(seeded_basic_db: Session, client: TestClient) -> None:
    generate_billing(seeded_basic_db, semester="2026/2027-Ganjil", semester_start=date(2026, 9, 1))

    # Mahasiswa 2401001 masih unpaid -> wajib DIBLOKIR
    elig_before = check_krs_eligibility(seeded_basic_db, "2401001")
    assert elig_before["eligible"] is False
    assert elig_before["krs_blocked"] is True
    assert elig_before["total_tunggakan"] == 5_000_000

    with pytest.raises(KrsBlockedError):
        submit_krs(
            seeded_basic_db,
            nim="2401001",
            semester="2026/2027-Ganjil",
            mata_kuliah=["Basis Data", "Algoritma"],
            total_sks=6,
        )

    # Uji juga via HTTP endpoint -> 403 Forbidden
    resp_blocked = client.post(
        "/api/krs/submit",
        json={
            "nim": "2401001",
            "semester": "2026/2027-Ganjil",
            "mata_kuliah": ["Basis Data", "Algoritma"],
            "total_sks": 6,
        },
    )
    assert resp_blocked.status_code == 403
    assert resp_blocked.json()["detail"]["krs_blocked"] is True

    # Lunasi tagihan -> mahasiswa kini diizinkan isi KRS (201 Created)
    billing = (
        seeded_basic_db.execute(select(Billing).join(Mahasiswa).where(Mahasiswa.nim == "2401001")).scalar_one()
    )
    process_payment(seeded_basic_db, billing.id, 5_000_000, "VA_BCA", transaction_id="TX-KRS-OK")

    resp_ok = client.post(
        "/api/krs/submit",
        json={
            "nim": "2401001",
            "semester": "2026/2027-Ganjil",
            "mata_kuliah": ["Basis Data", "Algoritma"],
            "total_sks": 6,
        },
    )
    assert resp_ok.status_code == 201
    assert resp_ok.json()["status"] == "approved"
