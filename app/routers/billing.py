"""Router untuk Billing Service, Mahasiswa, Payment Methods, dan APScheduler."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Billing, Mahasiswa, PaymentMethod, PaymentSource
from app.schemas import GenerateBillingRequest, MahasiswaCreateRequest, ManualPaymentRequest
from app.services.billing_service import (
    apply_overdue_and_penalties,
    generate_billing,
    process_payment,
)
from app.services.email_service import format_rupiah, send_payment_receipt
from app.services.scheduler_service import scheduler_manager

router = APIRouter(prefix="/api", tags=["Billing & Keuangan"])


@router.get("/payment-methods")
def list_payment_methods(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    methods = db.execute(select(PaymentMethod).order_by(PaymentMethod.id)).scalars().all()
    return [
        {
            "id": pm.id,
            "code": pm.code,
            "name": pm.name,
            "channel_type": pm.channel_type,
            "admin_fee": pm.admin_fee,
            "is_active": pm.is_active,
        }
        for pm in methods
    ]


@router.get("/mahasiswa")
def list_mahasiswa(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    students = db.execute(select(Mahasiswa).order_by(Mahasiswa.nim)).scalars().all()
    return [
        {
            "id": m.id,
            "nim": m.nim,
            "nama": m.nama,
            "email": m.email,
            "program_studi": m.program_studi,
            "angkatan": m.angkatan,
            "status_aktif": m.status_aktif,
        }
        for m in students
    ]


@router.post("/mahasiswa", status_code=201)
def create_mahasiswa(payload: MahasiswaCreateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    mhs = Mahasiswa(**payload.model_dump())
    db.add(mhs)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="NIM atau email sudah terdaftar.") from exc
    db.refresh(mhs)
    return {
        "id": mhs.id,
        "nim": mhs.nim,
        "nama": mhs.nama,
        "email": mhs.email,
        "program_studi": mhs.program_studi,
        "angkatan": mhs.angkatan,
        "status_aktif": mhs.status_aktif,
    }


@router.get("/billings")
def list_billings(
    semester: str | None = Query(default=None),
    status: str | None = Query(default=None),
    nim: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    stmt = (
        select(Billing)
        .options(joinedload(Billing.mahasiswa))
        .order_by(Billing.semester.desc(), Billing.id.asc())
    )
    if semester:
        stmt = stmt.where(Billing.semester == semester)
    if status:
        stmt = stmt.where(Billing.status == status)
    if nim:
        stmt = stmt.join(Mahasiswa).where(Mahasiswa.nim == nim)

    rows = db.execute(stmt).scalars().all()
    return [
        {
            "id": b.id,
            "billing_code": b.billing_code,
            "mahasiswa_id": b.mahasiswa_id,
            "nim": b.mahasiswa.nim,
            "nama": b.mahasiswa.nama,
            "program_studi": b.mahasiswa.program_studi,
            "semester": b.semester,
            "semester_start": b.semester_start.isoformat(),
            "base_amount": b.base_amount,
            "penalty_amount": b.penalty_amount,
            "total_amount": b.total_amount,
            "paid_amount": b.paid_amount,
            "remaining_amount": b.remaining_amount,
            "due_date": b.due_date.isoformat(),
            "status": b.status,
        }
        for b in rows
    ]


@router.post("/billing/generate")
def api_generate_billing(
    payload: GenerateBillingRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Generate tagihan SPP per semester untuk seluruh mahasiswa aktif."""
    return generate_billing(db, semester=payload.semester, semester_start=payload.semester_start)


@router.post("/billing/pay")
def api_manual_payment(
    payload: ManualPaymentRequest,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Record pembayaran SPP manual (dalam transaksi DB atomik + kirim email receipt)."""
    try:
        result = process_payment(
            db=db,
            billing_id=payload.billing_id,
            amount=payload.amount,
            method=payload.method,
            transaction_id=payload.transaction_id,
            source=PaymentSource.MANUAL.value,
            notes=payload.notes or "Pembayaran manual via loket/admin keuangan",
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    receipt_info = None
    if not result.duplicate:
        billing_full = db.execute(
            select(Billing)
            .options(joinedload(Billing.mahasiswa))
            .where(Billing.id == result.billing.id)
        ).scalar_one()
        pm = db.get(PaymentMethod, result.payment.payment_method_id)
        email_log = send_payment_receipt(
            db=db,
            mahasiswa=billing_full.mahasiswa,
            billing=billing_full,
            payment=result.payment,
            payment_method_name=pm.name if pm else payload.method,
        )
        receipt_info = {
            "email_log_id": email_log.id,
            "recipient": email_log.recipient_email,
            "delivery_status": email_log.delivery_status,
            "receipt_file": email_log.receipt_file_path,
        }

    return {
        "message": f"Pembayaran manual {format_rupiah(result.payment.amount)} berhasil dicatat.",
        "duplicate": result.duplicate,
        "transaction_id": result.payment.transaction_id,
        "billing_id": result.billing.id,
        "billing_code": result.billing.billing_code,
        "previous_status": result.previous_status,
        "new_status": result.new_status,
        "paid_amount": result.billing.paid_amount,
        "total_amount": result.billing.total_amount,
        "remaining_amount": result.billing.remaining_amount,
        "receipt": receipt_info,
    }


@router.post("/billing/apply-overdue")
def api_apply_overdue(
    as_of_date: date | None = Query(default=None),
    send_reminders: bool = Query(default=True),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Menjalankan perhitungan denda keterlambatan, update status overdue, dan kirim reminder."""
    return apply_overdue_and_penalties(db, as_of_date=as_of_date, send_reminders=send_reminders)


@router.get("/scheduler/jobs")
def get_scheduler_jobs() -> dict[str, Any]:
    """Menampilkan daftar cron job APScheduler yang aktif."""
    return {
        "scheduler_running": scheduler_manager.scheduler.running,
        "jobs": scheduler_manager.get_jobs_info(),
    }
