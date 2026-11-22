"""Test Deliverable 1: Payment Schema (DDL SQL & ORM Constraints)."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Billing, BillingStatus, Mahasiswa, Payment, PaymentMethod


def test_raw_schema_sql_executes_cleanly(tmp_path: Path) -> None:
    schema_path = Path(__file__).resolve().parent.parent / "schema.sql"
    sql_script = schema_path.read_text(encoding="utf-8")

    conn = sqlite3.connect(tmp_path / "raw_schema_test.db")
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(sql_script)

        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert {"billing", "payment", "payment_method", "mahasiswa", "krs_enrollment", "email_log"}.issubset(
            tables
        )

        # Pastikan CHECK constraint status menolak status tidak valid
        conn.execute(
            "INSERT INTO mahasiswa (nim, nama, email, program_studi) VALUES ('9901', 'Test', 't@k.ac.id', 'Teknik')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO billing
                (billing_code, mahasiswa_id, semester, semester_start, base_amount, total_amount, due_date, status)
                VALUES ('INV-ERR', 1, '20261', '2026-09-01', 5000000, 5000000, '2026-09-15', 'invalid_status')
                """
            )
    finally:
        conn.close()


def test_orm_status_and_unique_constraints(seeded_basic_db: Session) -> None:
    mhs = seeded_basic_db.query(Mahasiswa).filter_by(nim="2401001").one()
    pm = seeded_basic_db.query(PaymentMethod).filter_by(code="VA_BCA").one()

    b1 = Billing(
        billing_code="INV-TEST-1",
        mahasiswa_id=mhs.id,
        semester="2026/2027-Ganjil",
        semester_start=date(2026, 9, 1),
        base_amount=5_000_000,
        penalty_amount=0,
        total_amount=5_000_000,
        paid_amount=0,
        due_date=date(2026, 9, 15),
        status=BillingStatus.UNPAID.value,
    )
    seeded_basic_db.add(b1)
    seeded_basic_db.commit()

    # Duplikat billing untuk mahasiswa & semester sama harus ditolak
    b_dup = Billing(
        billing_code="INV-TEST-2",
        mahasiswa_id=mhs.id,
        semester="2026/2027-Ganjil",
        semester_start=date(2026, 9, 1),
        base_amount=5_000_000,
        penalty_amount=0,
        total_amount=5_000_000,
        paid_amount=0,
        due_date=date(2026, 9, 15),
        status=BillingStatus.UNPAID.value,
    )
    seeded_basic_db.add(b_dup)
    with pytest.raises(IntegrityError):
        seeded_basic_db.commit()
    seeded_basic_db.rollback()

    # Payment amount <= 0 harus ditolak oleh CHECK constraint
    bad_pay = Payment(
        billing_id=b1.id,
        payment_method_id=pm.id,
        transaction_id="TX-BAD-0",
        amount=0,
    )
    seeded_basic_db.add(bad_pay)
    with pytest.raises(IntegrityError):
        seeded_basic_db.commit()
    seeded_basic_db.rollback()
