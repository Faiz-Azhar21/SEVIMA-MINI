"""Deliverable 5: AI Financial Report (5%) - Step 3: AI Financial Insights.

Input:
- payment_data (CSV dengan kolom: nim, jumlah, tanggal, status)

Output JSON untuk dashboard frontend:
- Total revenue bulan ini: Rp X
- Collection rate: Y% mahasiswa sudah bayar
- Top 10 mahasiswa dengan tunggakan terbesar
- Rekomendasi: 'Kirim reminder ke Z mahasiswa dengan tunggakan >2 bulan'

Pendekatan Hybrid:
- Perhitungan angka & agregasi dilakukan secara deterministik menggunakan Pandas agar 100% akurat.
- Narasi & rekomendasi strategis diperkaya oleh LLM (opsional jika GEMINI_API_KEY / OPENAI_API_KEY tersedia)
  atau engine analitik lokal sebagai fallback deterministik.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.config import DATA_DIR, GEMINI_API_KEY, OPENAI_API_KEY
from app.models import Billing, BillingStatus, Mahasiswa, Payment, PaymentTxStatus
from app.services.email_service import format_rupiah

REQUIRED_CSV_COLUMNS = {"nim", "jumlah", "tanggal", "status"}
UNPAID_STATUSES = {"unpaid", "partial", "overdue"}
OVERDUE_TWO_MONTHS_DAYS = 60


def export_live_payment_csv(db: Session) -> str:
    """Mengekspor data pembayaran & tunggakan live database ke CSV berkolom (nim, jumlah, tanggal, status)."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["nim", "jumlah", "tanggal", "status"])

    # 1. Record pembayaran yang sudah berhasil (untuk revenue & status paid)
    payments = (
        db.execute(
            select(Payment)
            .options(joinedload(Payment.billing).joinedload(Billing.mahasiswa))
            .where(Payment.status == PaymentTxStatus.SUCCESS.value)
            .order_by(Payment.paid_at.asc())
        )
        .scalars()
        .all()
    )
    for p in payments:
        if not p.billing or not p.billing.mahasiswa:
            continue
        writer.writerow(
            [
                p.billing.mahasiswa.nim,
                p.amount,
                p.paid_at.date().isoformat(),
                "paid",
            ]
        )

    # 2. Record sisa tunggakan untuk billing yang belum lunas
    open_billings = (
        db.execute(
            select(Billing)
            .options(joinedload(Billing.mahasiswa))
            .where(Billing.status != BillingStatus.PAID.value)
            .order_by(Billing.due_date.asc())
        )
        .scalars()
        .all()
    )
    for b in open_billings:
        if b.remaining_amount <= 0:
            continue
        writer.writerow(
            [
                b.mahasiswa.nim,
                b.remaining_amount,
                b.due_date.isoformat(),
                b.status,
            ]
        )

    return output.getvalue()


def _try_llm_enrichment(metrics_payload: dict[str, Any]) -> tuple[str, list[str] | None]:
    """Opsional: memanggil LLM (Gemini/OpenAI) untuk memperkaya insight naratif jika API key diset."""
    prompt = (
        "Kamu adalah analis keuangan kampus. Berdasarkan metrik SPP berikut (JSON), "
        "berikan tepat 3 poin insight & rekomendasi taktis dalam Bahasa Indonesia sebagai JSON array of strings.\n"
        f"Data: {json.dumps(metrics_payload, ensure_ascii=False)}"
    )

    if GEMINI_API_KEY:
        try:
            url = (
                "https://generativelanguage.googleapis.com/v1beta/models/"
                f"gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
            )
            resp = httpx.post(
                url,
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=12.0,
            )
            if resp.status_code == 200:
                text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                parsed = _extract_json_list(text)
                if parsed:
                    return "hybrid-gemini", parsed
        except Exception:
            pass

    if OPENAI_API_KEY:
        try:
            resp = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                },
                timeout=12.0,
            )
            if resp.status_code == 200:
                text = resp.json()["choices"][0]["message"]["content"]
                parsed = _extract_json_list(text)
                if parsed:
                    return "hybrid-openai", parsed
        except Exception:
            pass

    return "hybrid-local-analytics", None


def _extract_json_list(raw_text: str) -> list[str] | None:
    start = raw_text.find("[")
    end = raw_text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        items = json.loads(raw_text[start : end + 1])
        if isinstance(items, list) and all(isinstance(x, str) for x in items):
            return items[:5]
    except json.JSONDecodeError:
        return None
    return None


def analyze_payment_csv(
    csv_content: str,
    *,
    reference_date: date | None = None,
    student_lookup: dict[str, dict[str, str]] | None = None,
    use_external_llm: bool = True,
) -> dict[str, Any]:
    """Menganalisis CSV `payment_data` (nim, jumlah, tanggal, status) menjadi JSON laporan keuangan."""
    ref_date = reference_date or date.today()
    df = pd.read_csv(io.StringIO(csv_content), dtype={"nim": str})
    df.columns = [str(c).strip().lower() for c in df.columns]

    missing = REQUIRED_CSV_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"CSV tidak valid. Kolom wajib yang hilang: {', '.join(sorted(missing))}")

    if df.empty:
        return {
            "generated_at": datetime.now().isoformat(),
            "period_month": ref_date.strftime("%Y-%m"),
            "engine": "hybrid-local-analytics",
            "summary": {
                "total_revenue_bulan_ini": 0,
                "total_revenue_bulan_ini_formatted": format_rupiah(0),
                "total_revenue_keseluruhan": 0,
                "total_revenue_keseluruhan_formatted": format_rupiah(0),
                "collection_rate_percent": 0.0,
                "collection_rate_text": "0.0% mahasiswa sudah bayar",
                "paid_students_count": 0,
                "total_students_count": 0,
                "total_outstanding_amount": 0,
                "total_outstanding_formatted": format_rupiah(0),
            },
            "top_10_tunggakan": [],
            "tunggakan_lebih_2_bulan": {"count": 0, "nims": []},
            "rekomendasi": "Kirim reminder ke 0 mahasiswa dengan tunggakan >2 bulan",
            "ai_narrative_insights": ["Belum ada data pembayaran yang tersedia untuk dianalisis."],
        }

    df["nim"] = df["nim"].astype(str).str.strip()
    df["jumlah"] = pd.to_numeric(df["jumlah"], errors="coerce").fillna(0).astype(int)
    df["status"] = df["status"].astype(str).str.strip().str.lower()
    df["tanggal_dt"] = pd.to_datetime(df["tanggal"], errors="coerce")
    df = df.dropna(subset=["tanggal_dt"])

    # 1. Total revenue bulan ini (status == 'paid' pada bulan & tahun ref_date)
    paid_df = df[df["status"] == "paid"]
    paid_this_month_df = paid_df[
        (paid_df["tanggal_dt"].dt.year == ref_date.year)
        & (paid_df["tanggal_dt"].dt.month == ref_date.month)
    ]
    total_revenue_bulan_ini = int(paid_this_month_df["jumlah"].sum())
    total_revenue_keseluruhan = int(paid_df["jumlah"].sum())

    # 2. Collection rate (% mahasiswa yang sudah bayar lunas / tanpa tunggakan aktif)
    all_nims = set(df["nim"].unique())
    unpaid_df = df[df["status"].isin(UNPAID_STATUSES) & (df["jumlah"] > 0)].copy()
    unpaid_nims = set(unpaid_df["nim"].unique())
    paid_nims = set(paid_df["nim"].unique()) - unpaid_nims

    total_students = len(all_nims)
    paid_students_count = len(paid_nims)
    collection_rate = round((paid_students_count / total_students) * 100, 1) if total_students else 0.0

    # 3. Top 10 mahasiswa dengan tunggakan terbesar & hitung tunggakan >2 bulan (>60 hari)
    top_10_list: list[dict[str, Any]] = []
    overdue_over_2_months_nims: list[str] = []
    total_outstanding = int(unpaid_df["jumlah"].sum())

    if not unpaid_df.empty:
        ref_ts = pd.Timestamp(ref_date)
        unpaid_df["days_outstanding"] = (ref_ts - unpaid_df["tanggal_dt"]).dt.days.clip(lower=0)

        grouped = (
            unpaid_df.groupby("nim", as_index=False)
            .agg(
                total_tunggakan=("jumlah", "sum"),
                earliest_date=("tanggal_dt", "min"),
                max_days=("days_outstanding", "max"),
                status=("status", lambda s: "overdue" if "overdue" in set(s) else s.iloc[0]),
            )
            .sort_values(by=["total_tunggakan", "max_days"], ascending=[False, False])
        )

        over_2m_df = grouped[grouped["max_days"] > OVERDUE_TWO_MONTHS_DAYS]
        overdue_over_2_months_nims = over_2m_df["nim"].tolist()

        lookup = student_lookup or {}
        for rank, row in enumerate(grouped.head(10).itertuples(index=False), start=1):
            info = lookup.get(row.nim, {})
            months_late = round(float(row.max_days) / 30.0, 1)
            top_10_list.append(
                {
                    "rank": rank,
                    "nim": row.nim,
                    "nama": info.get("nama", f"Mahasiswa {row.nim}"),
                    "program_studi": info.get("program_studi", "-"),
                    "total_tunggakan": int(row.total_tunggakan),
                    "total_tunggakan_formatted": format_rupiah(int(row.total_tunggakan)),
                    "status": row.status,
                    "tanggal_referensi": row.earliest_date.strftime("%Y-%m-%d"),
                    "lama_tunggakan_hari": int(row.max_days),
                    "lama_tunggakan_bulan": months_late,
                }
            )

    z_count = len(overdue_over_2_months_nims)
    rekomendasi_utama = f"Kirim reminder ke {z_count} mahasiswa dengan tunggakan >2 bulan"

    # Susun narasi analitik (deterministic + optional LLM enrichment)
    default_insights = [
        (
            f"Total penerimaan SPP bulan {ref_date.strftime('%B %Y')} tercatat "
            f"{format_rupiah(total_revenue_bulan_ini)} dari total akumulasi {format_rupiah(total_revenue_keseluruhan)}."
        ),
        (
            f"Tingkat kolektibilitas (collection rate) berada di angka {collection_rate:.1f}% "
            f"({paid_students_count} dari {total_students} mahasiswa lunas), "
            f"dengan sisa piutang sebesar {format_rupiah(total_outstanding)}."
        ),
        (
            f"Prioritas penagihan: terdapat {z_count} mahasiswa menunggak lebih dari 2 bulan. "
            "Aktifkan blokir KRS otomatis dan kirim reminder email berkala untuk mempercepat pelunasan."
        ),
    ]

    engine_name = "hybrid-local-analytics"
    narrative = default_insights
    if use_external_llm and (GEMINI_API_KEY or OPENAI_API_KEY):
        engine_name, llm_notes = _try_llm_enrichment(
            {
                "period_month": ref_date.strftime("%Y-%m"),
                "total_revenue_bulan_ini": total_revenue_bulan_ini,
                "collection_rate_percent": collection_rate,
                "total_outstanding": total_outstanding,
                "tunggakan_lebih_2_bulan_count": z_count,
                "top_3_tunggakan": top_10_list[:3],
            }
        )
        if llm_notes:
            narrative = llm_notes

    return {
        "generated_at": datetime.now().isoformat(),
        "period_month": ref_date.strftime("%Y-%m"),
        "engine": engine_name,
        "summary": {
            "total_revenue_bulan_ini": total_revenue_bulan_ini,
            "total_revenue_bulan_ini_formatted": format_rupiah(total_revenue_bulan_ini),
            "total_revenue_keseluruhan": total_revenue_keseluruhan,
            "total_revenue_keseluruhan_formatted": format_rupiah(total_revenue_keseluruhan),
            "collection_rate_percent": collection_rate,
            "collection_rate_text": f"{collection_rate:.1f}% mahasiswa sudah bayar",
            "paid_students_count": paid_students_count,
            "total_students_count": total_students,
            "total_outstanding_amount": total_outstanding,
            "total_outstanding_formatted": format_rupiah(total_outstanding),
        },
        "top_10_tunggakan": top_10_list,
        "tunggakan_lebih_2_bulan": {
            "count": z_count,
            "nims": overdue_over_2_months_nims,
        },
        "rekomendasi": rekomendasi_utama,
        "ai_narrative_insights": narrative,
    }


def generate_ai_report_from_db(
    db: Session,
    *,
    reference_date: date | None = None,
    use_external_llm: bool = True,
) -> dict[str, Any]:
    """Menjalankan AI Financial Report langsung dari data live database (via ekspor CSV)."""
    csv_text = export_live_payment_csv(db)
    students = db.execute(select(Mahasiswa)).scalars().all()
    lookup = {m.nim: {"nama": m.nama, "program_studi": m.program_studi} for m in students}
    report = analyze_payment_csv(
        csv_text,
        reference_date=reference_date,
        student_lookup=lookup,
        use_external_llm=use_external_llm,
    )
    report["data_source"] = "live_database_csv"
    return report


def generate_ai_report_from_file(
    csv_path: Path | None = None,
    *,
    db: Session | None = None,
    reference_date: date | None = None,
    use_external_llm: bool = True,
) -> dict[str, Any]:
    """Menjalankan AI Financial Report dari file CSV (default: data/payment_data.csv)."""
    path = csv_path or (DATA_DIR / "payment_data.csv")
    csv_text = path.read_text(encoding="utf-8")
    lookup: dict[str, dict[str, str]] = {}
    if db is not None:
        students = db.execute(select(Mahasiswa)).scalars().all()
        lookup = {m.nim: {"nama": m.nama, "program_studi": m.program_studi} for m in students}
    report = analyze_payment_csv(
        csv_text,
        reference_date=reference_date,
        student_lookup=lookup,
        use_external_llm=use_external_llm,
    )
    report["data_source"] = str(path.name)
    return report
