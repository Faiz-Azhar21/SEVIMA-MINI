"""Deliverable 3: Dashboard Keuangan (20%).

Menyediakan agregasi data real-time untuk:
- KPI ringkasan keuangan keseluruhan
- Per mahasiswa: total tagihan, sudah bayar, sisa, status billing, status blokir KRS
- Per program studi: collection rate (% mahasiswa lunas & % nominal terkumpul)
- Grafik pembayaran per bulan
- Log email receipt & reminder
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session, joinedload

from app.models import Billing, BillingStatus, EmailLog, Mahasiswa, Payment, PaymentTxStatus
from app.services.email_service import format_rupiah


def get_dashboard_overview(db: Session, semester: str | None = None) -> dict[str, Any]:
    """Mengambil seluruh metrik dashboard real-time dalam satu panggilan konsisten."""
    billings_query = (
        select(Billing)
        .options(joinedload(Billing.mahasiswa))
        .order_by(Billing.semester.desc(), Billing.id.asc())
    )
    if semester:
        billings_query = billings_query.where(Billing.semester == semester)
    billings = db.execute(billings_query).scalars().all()

    payments_query = (
        select(Payment)
        .options(joinedload(Payment.billing).joinedload(Billing.mahasiswa), joinedload(Payment.payment_method))
        .where(Payment.status == PaymentTxStatus.SUCCESS.value)
        .order_by(desc(Payment.paid_at))
    )
    payments = db.execute(payments_query).scalars().all()

    # 1. Per Mahasiswa summary
    student_map: dict[int, dict[str, Any]] = {}
    all_students = db.execute(select(Mahasiswa).order_by(Mahasiswa.nim)).scalars().all()
    for mhs in all_students:
        student_map[mhs.id] = {
            "mahasiswa_id": mhs.id,
            "nim": mhs.nim,
            "nama": mhs.nama,
            "email": mhs.email,
            "program_studi": mhs.program_studi,
            "angkatan": mhs.angkatan,
            "status_aktif": mhs.status_aktif,
            "total_tagihan": 0,
            "total_denda": 0,
            "sudah_bayar": 0,
            "sisa": 0,
            "billing_count": 0,
            "status_ringkas": "paid",
            "krs_blocked": False,
            "billings": [],
        }

    for b in billings:
        entry = student_map.get(b.mahasiswa_id)
        if not entry:
            continue
        entry["total_tagihan"] += b.total_amount
        entry["total_denda"] += b.penalty_amount
        entry["sudah_bayar"] += b.paid_amount
        entry["sisa"] += b.remaining_amount
        entry["billing_count"] += 1
        entry["billings"].append(
            {
                "billing_id": b.id,
                "billing_code": b.billing_code,
                "semester": b.semester,
                "base_amount": b.base_amount,
                "penalty_amount": b.penalty_amount,
                "total_amount": b.total_amount,
                "paid_amount": b.paid_amount,
                "remaining_amount": b.remaining_amount,
                "due_date": b.due_date.isoformat(),
                "status": b.status,
            }
        )

    per_mahasiswa: list[dict[str, Any]] = []
    status_priority = {"overdue": 4, "unpaid": 3, "partial": 2, "paid": 1}

    for entry in student_map.values():
        if entry["billing_count"] == 0:
            entry["status_ringkas"] = "no_billing"
            entry["krs_blocked"] = not entry["status_aktif"]
        else:
            worst = max(
                (b["status"] for b in entry["billings"]),
                key=lambda s: status_priority.get(s, 0),
            )
            entry["status_ringkas"] = worst
            entry["krs_blocked"] = (not entry["status_aktif"]) or (entry["sisa"] > 0) or (worst != "paid")

        entry["total_tagihan_formatted"] = format_rupiah(entry["total_tagihan"])
        entry["sudah_bayar_formatted"] = format_rupiah(entry["sudah_bayar"])
        entry["sisa_formatted"] = format_rupiah(entry["sisa"])
        per_mahasiswa.append(entry)

    # 2. Per Program Studi: Collection Rate
    prodi_agg: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "program_studi": "",
            "total_mahasiswa_tertagih": 0,
            "mahasiswa_lunas": 0,
            "mahasiswa_menunggak": 0,
            "total_tagihan": 0,
            "total_terbayar": 0,
            "total_sisa": 0,
        }
    )

    for mhs_entry in per_mahasiswa:
        if mhs_entry["billing_count"] == 0:
            continue
        prodi = mhs_entry["program_studi"]
        agg = prodi_agg[prodi]
        agg["program_studi"] = prodi
        agg["total_mahasiswa_tertagih"] += 1
        if mhs_entry["sisa"] == 0 and mhs_entry["status_ringkas"] == BillingStatus.PAID.value:
            agg["mahasiswa_lunas"] += 1
        else:
            agg["mahasiswa_menunggak"] += 1
        agg["total_tagihan"] += mhs_entry["total_tagihan"]
        agg["total_terbayar"] += mhs_entry["sudah_bayar"]
        agg["total_sisa"] += mhs_entry["sisa"]

    per_program_studi: list[dict[str, Any]] = []
    for prodi in sorted(prodi_agg.keys()):
        agg = prodi_agg[prodi]
        total_mhs = agg["total_mahasiswa_tertagih"]
        total_tag = agg["total_tagihan"]
        student_rate = round((agg["mahasiswa_lunas"] / total_mhs) * 100, 1) if total_mhs else 0.0
        amount_rate = round((agg["total_terbayar"] / total_tag) * 100, 1) if total_tag else 0.0
        agg["collection_rate_students"] = student_rate
        agg["collection_rate_amount"] = amount_rate
        agg["collection_rate"] = student_rate
        agg["total_tagihan_formatted"] = format_rupiah(agg["total_tagihan"])
        agg["total_terbayar_formatted"] = format_rupiah(agg["total_terbayar"])
        agg["total_sisa_formatted"] = format_rupiah(agg["total_sisa"])
        per_program_studi.append(agg)

    # 3. Grafik Pembayaran per Bulan
    monthly_totals: dict[str, dict[str, Any]] = defaultdict(lambda: {"amount": 0, "count": 0})
    for p in payments:
        month_key = p.paid_at.strftime("%Y-%m")
        monthly_totals[month_key]["amount"] += p.amount
        monthly_totals[month_key]["count"] += 1

    monthly_chart: list[dict[str, Any]] = []
    for month_key in sorted(monthly_totals.keys()):
        dt = datetime.strptime(month_key, "%Y-%m")
        amt = monthly_totals[month_key]["amount"]
        monthly_chart.append(
            {
                "month": month_key,
                "label": dt.strftime("%b %Y"),
                "total_amount": amt,
                "total_amount_formatted": format_rupiah(amt),
                "transaction_count": monthly_totals[month_key]["count"],
            }
        )

    # 4. KPI Summary
    total_tagihan_all = sum(b.total_amount for b in billings)
    total_terbayar_all = sum(b.paid_amount for b in billings)
    total_sisa_all = sum(b.remaining_amount for b in billings)
    total_denda_all = sum(b.penalty_amount for b in billings)

    billed_students = [m for m in per_mahasiswa if m["billing_count"] > 0]
    paid_students = [m for m in billed_students if not m["krs_blocked"]]
    blocked_students = [m for m in billed_students if m["krs_blocked"]]

    status_counts = {
        "unpaid": sum(1 for b in billings if b.status == BillingStatus.UNPAID.value),
        "partial": sum(1 for b in billings if b.status == BillingStatus.PARTIAL.value),
        "paid": sum(1 for b in billings if b.status == BillingStatus.PAID.value),
        "overdue": sum(1 for b in billings if b.status == BillingStatus.OVERDUE.value),
    }

    overall_collection_rate = (
        round((len(paid_students) / len(billed_students)) * 100, 1) if billed_students else 0.0
    )
    overall_amount_rate = (
        round((total_terbayar_all / total_tagihan_all) * 100, 1) if total_tagihan_all else 0.0
    )

    recent_payments = [
        {
            "id": p.id,
            "transaction_id": p.transaction_id,
            "billing_id": p.billing_id,
            "billing_code": p.billing.billing_code if p.billing else "-",
            "nim": p.billing.mahasiswa.nim if p.billing and p.billing.mahasiswa else "-",
            "nama": p.billing.mahasiswa.nama if p.billing and p.billing.mahasiswa else "-",
            "method": p.payment_method.name if p.payment_method else "-",
            "source": p.source,
            "amount": p.amount,
            "amount_formatted": format_rupiah(p.amount),
            "paid_at": p.paid_at.isoformat(),
        }
        for p in payments[:15]
    ]

    recent_emails = [
        {
            "id": e.id,
            "recipient_email": e.recipient_email,
            "email_type": e.email_type,
            "subject": e.subject,
            "delivery_status": e.delivery_status,
            "receipt_file_path": e.receipt_file_path,
            "sent_at": e.sent_at.isoformat(),
        }
        for e in db.execute(select(EmailLog).order_by(desc(EmailLog.sent_at)).limit(15)).scalars().all()
    ]

    semesters = sorted({b.semester for b in billings}, reverse=True)

    return {
        "generated_at": datetime.now().isoformat(),
        "available_semesters": semesters,
        "summary": {
            "total_tagihan": total_tagihan_all,
            "total_tagihan_formatted": format_rupiah(total_tagihan_all),
            "total_terbayar": total_terbayar_all,
            "total_terbayar_formatted": format_rupiah(total_terbayar_all),
            "total_sisa": total_sisa_all,
            "total_sisa_formatted": format_rupiah(total_sisa_all),
            "total_denda": total_denda_all,
            "total_denda_formatted": format_rupiah(total_denda_all),
            "total_mahasiswa_tertagih": len(billed_students),
            "mahasiswa_lunas": len(paid_students),
            "mahasiswa_diblokir_krs": len(blocked_students),
            "collection_rate_students": overall_collection_rate,
            "collection_rate_amount": overall_amount_rate,
            "status_counts": status_counts,
        },
        "per_mahasiswa": per_mahasiswa,
        "per_program_studi": per_program_studi,
        "monthly_chart": monthly_chart,
        "recent_payments": recent_payments,
        "recent_emails": recent_emails,
    }
