"""Test Deliverable 5: AI Financial Report (CSV -> JSON untuk Dashboard Frontend)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from app.services.ai_report_service import analyze_payment_csv, generate_ai_report_from_file


def test_analyze_sample_payment_csv_matches_spec() -> None:
    sample_path = Path(__file__).resolve().parent.parent / "data" / "payment_data.csv"
    report = generate_ai_report_from_file(
        sample_path,
        reference_date=date(2026, 11, 23),
        use_external_llm=False,
    )

    # 1. Total revenue bulan ini (Nov 2026):
    # 3 Teknik paid (15jt) + 3 Ekonomi paid (12jt) + 3 partial paid in Nov (2.5jt + 2jt + 1.5jt = 6jt) = 33jt
    assert report["summary"]["total_revenue_bulan_ini"] == 33_000_000
    assert report["summary"]["total_revenue_bulan_ini_formatted"] == "Rp 33.000.000"

    # 2. Collection rate (% mahasiswa sudah bayar lunas)
    # Total 23 mahasiswa unik, 11 lunas penuh -> 47.8%
    assert report["summary"]["paid_students_count"] == 11
    assert report["summary"]["total_students_count"] == 23
    assert report["summary"]["collection_rate_percent"] == 47.8
    assert report["summary"]["collection_rate_text"] == "47.8% mahasiswa sudah bayar"

    # 3. Top 10 mahasiswa dengan tunggakan terbesar (harus tepat 10 dan urut menurun)
    top10 = report["top_10_tunggakan"]
    assert len(top10) == 10
    amounts = [item["total_tunggakan"] for item in top10]
    assert amounts == sorted(amounts, reverse=True)
    # Mahasiswa dengan 2 semester overdue (Rp 8.800.000) berada di peringkat teratas
    assert top10[0]["total_tunggakan"] == 8_800_000

    # 4. Rekomendasi untuk tunggakan >2 bulan (6 mahasiswa overdue sejak Sept/Jul 2026)
    assert report["tunggakan_lebih_2_bulan"]["count"] == 6
    assert report["rekomendasi"] == "Kirim reminder ke 6 mahasiswa dengan tunggakan >2 bulan"


def test_ai_report_endpoints_and_csv_upload(client: TestClient) -> None:
    # GET sample_csv endpoint
    resp = client.get("/api/ai-report?source=sample_csv")
    assert resp.status_code == 200
    body = resp.json()
    assert "summary" in body
    assert "top_10_tunggakan" in body
    assert body["rekomendasi"].startswith("Kirim reminder ke ")

    # POST upload CSV valid
    custom_csv = (
        "nim,jumlah,tanggal,status\n"
        "2401001,5000000,2026-11-10,paid\n"
        "2401002,5000000,2026-08-01,overdue\n"
    )
    upload_resp = client.post(
        "/api/ai-report/analyze-csv",
        files={"file": ("custom.csv", custom_csv.encode("utf-8"), "text/csv")},
    )
    assert upload_resp.status_code == 200
    up_json = upload_resp.json()
    assert up_json["summary"]["collection_rate_percent"] == 50.0
    assert up_json["tunggakan_lebih_2_bulan"]["count"] == 1

    # POST upload CSV dengan kolom salah -> 400 Bad Request
    bad_csv = "student_id,amount\n1,1000\n"
    bad_resp = client.post(
        "/api/ai-report/analyze-csv",
        files={"file": ("bad.csv", bad_csv.encode("utf-8"), "text/csv")},
    )
    assert bad_resp.status_code == 400
