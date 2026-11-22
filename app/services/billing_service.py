"""Deliverable 2: Billing Service (35%).

Mencakup:
1. generate_billing       - Generate tagihan SPP per semester untuk mahasiswa aktif
2. process_payment        - Record pembayaran manual/webhook secara atomik (DB transaction)
3. calculate_late_fee     - Kalkulasi denda keterlambatan
4. apply_overdue_and_penalties - Update status overdue, denda, dan kirim reminder otomatis
5. check_krs_eligibility & submit_krs - Block KRS jika ada tunggakan
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.config import (
    BILLING_DUE_DAYS,
    DEFAULT_SPP_TARIFF,
    LATE_FEE_DAILY_RATE,
    LATE_FEE_MAX_RATE,
    REMINDER_DAYS_BEFORE_DUE,
    SPP_TARIFF_BY_PRODI,
)
from app.database import atomic_transaction
from app.models import (
    Billing,
    BillingStatus,
    KrsEnrollment,
    Mahasiswa,
    Payment,
    PaymentMethod,
    PaymentSource,
    PaymentTxStatus,
)
from app.services.email_service import format_rupiah, send_payment_reminder
from app.services.realtime import realtime_broker


class KrsBlockedError(Exception):
    """Dilempar ketika mahasiswa diblokir dari pengisian KRS karena memiliki tunggakan."""

    def __init__(self, message: str, eligibility: dict[str, Any]) -> None:
        super().__init__(message)
        self.eligibility = eligibility


@dataclass
class PaymentProcessResult:
    payment: Payment
    billing: Billing
    previous_status: str
    new_status: str
    duplicate: bool = False


def get_spp_amount_for_prodi(program_studi: str) -> int:
    """Menentukan tarif SPP berdasarkan program_studi (Teknik: 5jt, Ekonomi: 4jt)."""
    normalized = program_studi.strip().lower()
    for prodi_name, tariff in SPP_TARIFF_BY_PRODI.items():
        if prodi_name.lower() == normalized or prodi_name.lower() in normalized:
            return tariff
    return DEFAULT_SPP_TARIFF


def _make_billing_code(semester: str, nim: str) -> str:
    clean_sem = "".join(ch for ch in semester if ch.isalnum()).upper()[:16]
    return f"INV-{clean_sem}-{nim}"


def generate_billing(
    db: Session,
    semester: str,
    semester_start: date,
) -> dict[str, Any]:
    """Step 1: Generate tagihan SPP awal semester untuk semua mahasiswa aktif.

    Aturan:
    - Hanya untuk mahasiswa dengan `status_aktif == True`
    - Nominal berdasarkan `program_studi` (Teknik: Rp 5.000.000, Ekonomi: Rp 4.000.000)
    - `due_date`: 2 minggu (14 hari) setelah `semester_start`
    - Status awal: 'unpaid'
    - Idempoten: skip mahasiswa yang sudah memiliki tagihan pada semester tersebut
    """
    due_date = semester_start + timedelta(days=BILLING_DUE_DAYS)

    active_students = (
        db.execute(select(Mahasiswa).where(Mahasiswa.status_aktif.is_(True)).order_by(Mahasiswa.nim))
        .scalars()
        .all()
    )

    existing_ids = set(
        db.execute(select(Billing.mahasiswa_id).where(Billing.semester == semester)).scalars().all()
    )

    created_billings: list[Billing] = []
    skipped_count = 0

    with atomic_transaction(db):
        for mhs in active_students:
            if mhs.id in existing_ids:
                skipped_count += 1
                continue

            base_amount = get_spp_amount_for_prodi(mhs.program_studi)
            billing = Billing(
                billing_code=_make_billing_code(semester, mhs.nim),
                mahasiswa_id=mhs.id,
                semester=semester,
                semester_start=semester_start,
                base_amount=base_amount,
                penalty_amount=0,
                total_amount=base_amount,
                paid_amount=0,
                due_date=due_date,
                status=BillingStatus.UNPAID.value,
            )
            db.add(billing)
            created_billings.append(billing)

    for b in created_billings:
        db.refresh(b)

    if created_billings:
        realtime_broker.publish(
            "billing_generated",
            {"semester": semester, "created_count": len(created_billings)},
        )

    return {
        "semester": semester,
        "semester_start": semester_start.isoformat(),
        "due_date": due_date.isoformat(),
        "active_students_checked": len(active_students),
        "created_count": len(created_billings),
        "skipped_existing_count": skipped_count,
        "created_billing_codes": [b.billing_code for b in created_billings],
    }


def calculate_late_fee(
    base_amount: int,
    due_date: date,
    as_of_date: date | None = None,
    current_status: str = BillingStatus.UNPAID.value,
) -> dict[str, Any]:
    """Hitung denda keterlambatan untuk sebuah tagihan.

    Tarif denda: 0.5% per hari keterlambatan dari base_amount, maksimal 10% (cap).
    """
    ref_date = as_of_date or date.today()
    if current_status == BillingStatus.PAID.value or ref_date <= due_date:
        return {
            "days_late": 0,
            "penalty_amount": 0,
            "daily_rate": LATE_FEE_DAILY_RATE,
            "max_cap_amount": int(round(base_amount * LATE_FEE_MAX_RATE)),
            "is_overdue": False,
        }

    days_late = (ref_date - due_date).days
    raw_penalty = int(round(base_amount * LATE_FEE_DAILY_RATE * days_late))
    max_cap = int(round(base_amount * LATE_FEE_MAX_RATE))
    penalty = min(raw_penalty, max_cap)

    return {
        "days_late": days_late,
        "penalty_amount": penalty,
        "daily_rate": LATE_FEE_DAILY_RATE,
        "max_cap_amount": max_cap,
        "is_overdue": True,
    }


def apply_overdue_and_penalties(
    db: Session,
    as_of_date: date | None = None,
    send_reminders: bool = True,
) -> dict[str, Any]:
    """Menandai tagihan lewat jatuh tempo sebagai 'overdue', menghitung denda, dan mengirim reminder."""
    ref_date = as_of_date or date.today()
    open_billings = (
        db.execute(
            select(Billing)
            .options(joinedload(Billing.mahasiswa))
            .where(Billing.status != BillingStatus.PAID.value)
        )
        .scalars()
        .all()
    )

    overdue_updated = 0
    total_penalty_applied = 0
    reminder_targets: list[tuple[Mahasiswa, Billing, str]] = []

    with atomic_transaction(db):
        for billing in open_billings:
            if ref_date > billing.due_date:
                calc = calculate_late_fee(
                    base_amount=billing.base_amount,
                    due_date=billing.due_date,
                    as_of_date=ref_date,
                    current_status=billing.status,
                )
                new_penalty = max(billing.penalty_amount, calc["penalty_amount"])
                new_total = billing.base_amount + new_penalty
                changed = (
                    new_penalty != billing.penalty_amount
                    or new_total != billing.total_amount
                    or billing.status != BillingStatus.OVERDUE.value
                )
                billing.penalty_amount = new_penalty
                billing.total_amount = new_total
                if billing.paid_amount < billing.total_amount:
                    billing.status = BillingStatus.OVERDUE.value
                billing.updated_at = datetime.now()

                if changed:
                    overdue_updated += 1
                total_penalty_applied += new_penalty
                if send_reminders:
                    reminder_targets.append(
                        (
                            billing.mahasiswa,
                            billing,
                            f"Tunggakan melewati jatuh tempo ({calc['days_late']} hari)",
                        )
                    )
            else:
                days_until_due = (billing.due_date - ref_date).days
                if send_reminders and 0 <= days_until_due <= REMINDER_DAYS_BEFORE_DUE:
                    reminder_targets.append(
                        (
                            billing.mahasiswa,
                            billing,
                            f"Jatuh tempo dalam {days_until_due} hari",
                        )
                    )

    reminders_sent = 0
    for mhs, billing, reason in reminder_targets:
        send_payment_reminder(db, mhs, billing, reason=reason)
        reminders_sent += 1

    if overdue_updated > 0:
        realtime_broker.publish(
            "overdue_updated",
            {"overdue_updated": overdue_updated, "reminders_sent": reminders_sent},
        )

    return {
        "as_of_date": ref_date.isoformat(),
        "open_billings_checked": len(open_billings),
        "overdue_updated": overdue_updated,
        "total_penalty_amount": total_penalty_applied,
        "reminders_sent": reminders_sent,
    }


def _resolve_payment_method(db: Session, method: str | int) -> PaymentMethod:
    if isinstance(method, int):
        pm = db.get(PaymentMethod, method)
    else:
        method_str = str(method).strip()
        if method_str.isdigit():
            pm = db.get(PaymentMethod, int(method_str))
        else:
            pm = db.execute(
                select(PaymentMethod).where(PaymentMethod.code.ilike(method_str))
            ).scalar_one_or_none()

    if not pm or not pm.is_active:
        raise ValueError(f"Metode pembayaran '{method}' tidak ditemukan atau tidak aktif")
    return pm


def process_payment(
    db: Session,
    billing_id: int,
    amount: int,
    method: str | int,
    *,
    transaction_id: str | None = None,
    source: str = PaymentSource.MANUAL.value,
    paid_at: datetime | None = None,
    notes: str | None = None,
    raw_payload: str | None = None,
) -> PaymentProcessResult:
    """Step 2: Memproses pembayaran secara atomik menggunakan database transaction.

    Aturan state management:
    - Akumulasi total_paid = billing.paid_amount + amount
    - Jika total_paid < billing.total -> status 'partial'
    - Jika total_paid >= billing.total -> status 'paid'
    - Membuat payment record & memperbarui billing dalam satu DB transaction.
    - Idempoten berdasarkan `transaction_id`.
    """
    if amount <= 0:
        raise ValueError("Nominal pembayaran harus lebih dari 0")

    tx_id = (transaction_id or f"PAY-{uuid.uuid4().hex[:12].upper()}").strip()

    # Cek idempotency: jika transaction_id sudah pernah tercatat sukses, kembalikan tanpa double-charge
    existing_payment = db.execute(
        select(Payment).options(joinedload(Payment.billing)).where(Payment.transaction_id == tx_id)
    ).scalar_one_or_none()
    if existing_payment is not None:
        return PaymentProcessResult(
            payment=existing_payment,
            billing=existing_payment.billing,
            previous_status=existing_payment.billing.status,
            new_status=existing_payment.billing.status,
            duplicate=True,
        )

    pm = _resolve_payment_method(db, method)
    payment_time = paid_at or datetime.now()

    with atomic_transaction(db):
        stmt = select(Billing).where(Billing.id == billing_id).with_for_update()
        billing = db.execute(stmt).scalar_one_or_none()
        if billing is None:
            raise LookupError(f"Billing dengan id={billing_id} tidak ditemukan")

        if billing.status == BillingStatus.PAID.value:
            raise ValueError(f"Billing {billing.billing_code} sudah berstatus 'paid'")

        previous_status = billing.status
        new_paid_amount = billing.paid_amount + amount
        if new_paid_amount < billing.total:
            new_status = BillingStatus.PARTIAL.value
        else:
            new_status = BillingStatus.PAID.value

        payment = Payment(
            billing_id=billing.id,
            payment_method_id=pm.id,
            transaction_id=tx_id,
            amount=amount,
            source=source,
            status=PaymentTxStatus.SUCCESS.value,
            paid_at=payment_time,
            notes=notes,
            raw_payload=raw_payload,
        )
        db.add(payment)

        billing.paid_amount = new_paid_amount
        billing.status = new_status
        billing.updated_at = datetime.now()
        db.flush()

    db.refresh(payment)
    db.refresh(billing)

    realtime_broker.publish(
        "payment_processed",
        {
            "billing_id": billing.id,
            "billing_code": billing.billing_code,
            "transaction_id": payment.transaction_id,
            "amount": payment.amount,
            "source": source,
            "previous_status": previous_status,
            "new_status": new_status,
        },
    )

    return PaymentProcessResult(
        payment=payment,
        billing=billing,
        previous_status=previous_status,
        new_status=new_status,
        duplicate=False,
    )


def check_krs_eligibility(db: Session, nim: str) -> dict[str, Any]:
    """Mengecek apakah mahasiswa diperbolehkan mengisi KRS (Block KRS jika ada tunggakan)."""
    mahasiswa = db.execute(
        select(Mahasiswa).options(selectinload(Mahasiswa.billings)).where(Mahasiswa.nim == nim)
    ).scalar_one_or_none()

    if mahasiswa is None:
        raise LookupError(f"Mahasiswa dengan NIM '{nim}' tidak ditemukan")

    if not mahasiswa.status_aktif:
        return {
            "nim": mahasiswa.nim,
            "nama": mahasiswa.nama,
            "program_studi": mahasiswa.program_studi,
            "eligible": False,
            "krs_blocked": True,
            "reason": "Status mahasiswa tidak aktif.",
            "total_tunggakan": 0,
            "total_tunggakan_formatted": format_rupiah(0),
            "unpaid_billings": [],
        }

    unpaid_billings = [
        b for b in mahasiswa.billings if b.status != BillingStatus.PAID.value or b.remaining_amount > 0
    ]
    total_tunggakan = sum(b.remaining_amount for b in unpaid_billings)

    if unpaid_billings:
        return {
            "nim": mahasiswa.nim,
            "nama": mahasiswa.nama,
            "program_studi": mahasiswa.program_studi,
            "eligible": False,
            "krs_blocked": True,
            "reason": (
                f"Akses KRS diblokir: masih terdapat {len(unpaid_billings)} tagihan belum lunas "
                f"dengan total tunggakan {format_rupiah(total_tunggakan)}."
            ),
            "total_tunggakan": total_tunggakan,
            "total_tunggakan_formatted": format_rupiah(total_tunggakan),
            "unpaid_billings": [
                {
                    "billing_id": b.id,
                    "billing_code": b.billing_code,
                    "semester": b.semester,
                    "status": b.status,
                    "total_amount": b.total_amount,
                    "paid_amount": b.paid_amount,
                    "remaining_amount": b.remaining_amount,
                    "due_date": b.due_date.isoformat(),
                }
                for b in unpaid_billings
            ],
        }

    return {
        "nim": mahasiswa.nim,
        "nama": mahasiswa.nama,
        "program_studi": mahasiswa.program_studi,
        "eligible": True,
        "krs_blocked": False,
        "reason": "Bebas tunggakan SPP. Mahasiswa diizinkan mengisi KRS.",
        "total_tunggakan": 0,
        "total_tunggakan_formatted": format_rupiah(0),
        "unpaid_billings": [],
    }


def submit_krs(
    db: Session,
    nim: str,
    semester: str,
    mata_kuliah: list[str],
    total_sks: int,
) -> dict[str, Any]:
    """Pengisian KRS mahasiswa — otomatis ditolak (Block KRS) jika masih memiliki tunggakan SPP."""
    eligibility = check_krs_eligibility(db, nim)
    if not eligibility["eligible"]:
        raise KrsBlockedError(eligibility["reason"], eligibility)

    mahasiswa = db.execute(select(Mahasiswa).where(Mahasiswa.nim == nim)).scalar_one()

    existing_krs = db.execute(
        select(KrsEnrollment).where(
            KrsEnrollment.mahasiswa_id == mahasiswa.id,
            KrsEnrollment.semester == semester,
        )
    ).scalar_one_or_none()
    if existing_krs:
        raise ValueError(f"KRS untuk NIM {nim} pada semester {semester} sudah terdaftar")

    with atomic_transaction(db):
        krs = KrsEnrollment(
            mahasiswa_id=mahasiswa.id,
            semester=semester,
            mata_kuliah=json.dumps(mata_kuliah, ensure_ascii=False),
            total_sks=total_sks,
            status="approved",
        )
        db.add(krs)

    db.refresh(krs)
    return {
        "krs_id": krs.id,
        "nim": mahasiswa.nim,
        "nama": mahasiswa.nama,
        "semester": krs.semester,
        "mata_kuliah": mata_kuliah,
        "total_sks": krs.total_sks,
        "status": krs.status,
        "created_at": krs.created_at.isoformat(),
    }
