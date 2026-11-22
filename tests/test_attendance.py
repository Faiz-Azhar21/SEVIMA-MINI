"""Automated tests memverifikasi seluruh Deliverable (100%) & Kriteria Sukses Minggu 12."""

from __future__ import annotations

import io
from datetime import datetime, time, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models import Course, Enrollment, Schedule, Student
from app.schemas import AttendanceScanRequest
from app.security import create_qr_jwt, scan_rate_limiter
from app.seed import seed_database
from app.services.attendance_service import record_attendance_scan
from app.services.qr_service import create_or_refresh_session_qr, generate_attendance_qr


@pytest.fixture()
def db_session():
    """Database SQLite in-memory terisolasi per test."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)
    db = TestingSessionLocal()
    seed_database(db)
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client(db_session):
    """TestClient FastAPI dengan override database in-memory dan rate limiter bersih."""
    scan_rate_limiter.reset()

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        test_client.close()
        app.dependency_overrides.clear()
        scan_rate_limiter.reset()


def _get_live_schedule_id(client: TestClient) -> int:
    meta = client.get("/attendance/meta").json()
    for sched in meta["schedules"]:
        if sched["in_scan_window"]:
            return sched["id"]
    # Fallback pastikan jadwal live aktif
    res = client.post("/attendance/schedules/demo-now")
    assert res.status_code == 200
    return res.json()["schedule_id"]


# ==============================================================================
# 1. DELIVERABLE 1: QR GENERATION SERVICE (30%)
# ==============================================================================


def test_generate_attendance_qr_helper_returns_valid_image_and_15m_jwt():
    qr_img, token = generate_attendance_qr(schedule_id=1, valid_minutes=15)
    assert qr_img is not None

    decoded = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    assert decoded["schedule_id"] == 1
    assert "jti" in decoded and len(decoded["jti"]) >= 16
    assert decoded["exp"] - decoded["iat"] == 15 * 60


def test_qr_endpoint_returns_valid_png_image_and_unique_token_per_generation(client: TestClient):
    schedule_id = _get_live_schedule_id(client)

    res1 = client.get(f"/attendance/qr/{schedule_id}")
    assert res1.status_code == 200
    assert res1.headers["content-type"] == "image/png"
    assert res1.content[:8] == b"\x89PNG\r\n\x1a\n"

    # Pastikan PNG valid dapat dibuka oleh Pillow
    img = Image.open(io.BytesIO(res1.content))
    assert img.width > 100 and img.height > 100

    token1 = res1.headers["X-Attendance-Token"]
    jti1 = res1.headers["X-Token-Jti"]

    # Generate ulang -> harus menghasilkan token & JTI unik baru (anti replay attack)
    res2 = client.get(f"/attendance/qr/{schedule_id}")
    assert res2.status_code == 200
    token2 = res2.headers["X-Attendance-Token"]
    jti2 = res2.headers["X-Token-Jti"]

    assert token1 != token2
    assert jti1 != jti2


def test_student_role_cannot_generate_qr(client: TestClient):
    schedule_id = _get_live_schedule_id(client)
    res = client.get(f"/attendance/qr/{schedule_id}", headers={"X-Role": "mahasiswa"})
    assert res.status_code == 403


# ==============================================================================
# 2. DELIVERABLE 2: ATTENDANCE RECORDING & VALIDATION (30%)
# ==============================================================================


def test_valid_scan_recorded_as_hadir_and_duplicate_rejected(client: TestClient):
    schedule_id = _get_live_schedule_id(client)
    qr_info = client.get(f"/attendance/qr/{schedule_id}/info").json()
    token = qr_info["token"]

    # Mahasiswa 2301001 terdaftar di IF203 (jadwal live)
    scan_res = client.post("/attendance/scan", json={"token": token, "nim": "2301001"})
    assert scan_res.status_code == 200
    body = scan_res.json()
    assert body["success"] is True
    assert body["status"] == "hadir"
    assert body["data"]["nim"] == "2301001"

    # Scan ulang oleh mahasiswa yang sama -> harus ditolak (409 Conflict)
    dup_res = client.post("/attendance/scan", json={"token": token, "nim": "2301001"})
    assert dup_res.status_code == 409


def test_student_cannot_scan_other_class_qr(client: TestClient):
    """Kriteria Sukses: Mahasiswa tidak bisa scan QR kelas orang lain."""
    schedule_id = _get_live_schedule_id(client)
    qr_info = client.get(f"/attendance/qr/{schedule_id}/info").json()

    # NIM 2301009 terdaftar di IF202, BUKAN di IF203
    res = client.post("/attendance/scan", json={"token": qr_info["token"], "nim": "2301009"})
    assert res.status_code == 403
    assert "tidak terdaftar" in res.json()["detail"].lower()


def test_hadir_vs_terlambat_vs_closed_window_and_wrong_day(db_session):
    """Menguji status Hadir (<=15m), Terlambat (15-30m), lewat batas (>30m), dan hari salah."""
    # Jadwal IF201 adalah Senin jam 07:00 - 09:30
    algo_sched = (
        db_session.query(Schedule)
        .join(Course)
        .filter(Course.code == "IF201")
        .first()
    )
    assert algo_sched is not None

    # Pilih tanggal Senin baru yang belum ada di seed (Senin minggu depan)
    monday_0700 = datetime(2026, 12, 7, 7, 0, tzinfo=settings.tz)
    assert monday_0700.weekday() == 0

    # 1) Dosen generate QR jam 07:00 -> Mahasiswa 2301001 scan jam 07:10 -> HADIR
    qr_1 = create_or_refresh_session_qr(db_session, algo_sched.id, 15, now_local=monday_0700)
    res_hadir = record_attendance_scan(
        db_session,
        AttendanceScanRequest(token=qr_1.token, nim="2301001"),
        now_local=monday_0700 + timedelta(minutes=10),
    )
    assert res_hadir.success is True
    assert res_hadir.status == "hadir"

    # 2) Dosen refresh QR jam 07:16 (valid 15 menit) -> Mahasiswa 2301002 scan jam 07:20 -> TERLAMBAT
    qr_2 = create_or_refresh_session_qr(
        db_session, algo_sched.id, 15, now_local=monday_0700 + timedelta(minutes=16)
    )
    res_late = record_attendance_scan(
        db_session,
        AttendanceScanRequest(token=qr_2.token, nim="2301002"),
        now_local=monday_0700 + timedelta(minutes=20),
    )
    assert res_late.success is True
    assert res_late.status == "terlambat"

    # 3) Anti-replay: token QR pertama (qr_1) sudah diganti qr_2 -> harus ditolak!
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as replay_err:
        record_attendance_scan(
            db_session,
            AttendanceScanRequest(token=qr_1.token, nim="2301003"),
            now_local=monday_0700 + timedelta(minutes=12),
        )
    assert replay_err.value.status_code == 401

    # 4) Scan jam 07:35 (lewat 30 menit, meski QR masih aktif) -> ditolak (400)
    qr_3 = create_or_refresh_session_qr(
        db_session, algo_sched.id, 15, now_local=monday_0700 + timedelta(minutes=31)
    )
    with pytest.raises(HTTPException) as closed_err:
        record_attendance_scan(
            db_session,
            AttendanceScanRequest(token=qr_3.token, nim="2301003"),
            now_local=monday_0700 + timedelta(minutes=35),
        )
    assert closed_err.value.status_code == 400
    assert "30 menit" in closed_err.value.detail

    # 5) Hari salah (Selasa untuk jadwal Senin) -> ditolak (400)
    tuesday_0705 = monday_0700 + timedelta(days=1, minutes=5)
    qr_wrong_day = create_or_refresh_session_qr(
        db_session, algo_sched.id, 15, now_local=tuesday_0705
    )
    with pytest.raises(HTTPException) as day_err:
        record_attendance_scan(
            db_session,
            AttendanceScanRequest(token=qr_wrong_day.token, nim="2301003"),
            now_local=tuesday_0705,
        )
    assert day_err.value.status_code == 400
    assert "tidak ada jadwal kuliah" in day_err.value.detail.lower()


def test_optional_geolocation_validation(client: TestClient):
    schedule_id = _get_live_schedule_id(client)
    qr_info = client.get(f"/attendance/qr/{schedule_id}/info").json()
    token = qr_info["token"]

    # Lokasi terlalu jauh (> 150 meter dari kampus -6.200000, 106.816666) -> ditolak (403)
    far_res = client.post(
        "/attendance/scan",
        json={
            "token": token,
            "nim": "2301002",
            "latitude": -6.250000,
            "longitude": 106.850000,
        },
    )
    assert far_res.status_code == 403
    assert "luar radius" in far_res.json()["detail"].lower()

    # Lokasi tepat di dalam radius kampus -> diterima (200)
    near_res = client.post(
        "/attendance/scan",
        json={
            "token": token,
            "nim": "2301002",
            "latitude": -6.200050,
            "longitude": 106.816700,
        },
    )
    assert near_res.status_code == 200
    assert near_res.json()["data"]["distance_meters"] < 150.0


# ==============================================================================
# 3. DELIVERABLE 3: ATTENDANCE REPORT & EXCEL EXPORT (20%)
# ==============================================================================


def test_student_and_course_reports_and_excel_export(client: TestClient):
    """Kriteria Sukses: Report presensi akurat dan bisa di-export ke Excel."""
    meta = client.get("/attendance/meta").json()
    algo_course = next(c for c in meta["courses"] if c["code"] == "IF201")

    # 1. Course report untuk IF201
    course_rep = client.get(f"/attendance/report/course/{algo_course['id']}").json()
    assert course_rep["total_sessions"] == 6
    assert course_rep["total_students"] == 8
    # Sesuai seed: 5 mahasiswa <75% (2301003, 2301004, 2301005, 2301006, 2301008)
    assert course_rep["warning_count"] == 5
    warning_nims = {s["nim"] for s in course_rep["warning_students"]}
    assert warning_nims == {"2301003", "2301004", "2301005", "2301006", "2301008"}

    # 2. Student report untuk NIM 2301003 (1/6 = 16.67% di IF201, 4/4 = 100% di IF202)
    stu_rep = client.get("/attendance/report/student/2301003").json()
    algo_item = next(c for c in stu_rep["courses"] if c["course_code"] == "IF201")
    assert algo_item["attendance_percentage"] == pytest.approx(16.67, abs=0.05)
    assert algo_item["warning"] is True

    db_item = next(c for c in stu_rep["courses"] if c["course_code"] == "IF202")
    assert db_item["attendance_percentage"] == 100.0
    assert db_item["warning"] is False

    # 3. Export Excel (.xlsx) dan validasi isi workbook dengan openpyxl
    export_res = client.get(f"/attendance/report/course/{algo_course['id']}/export")
    assert export_res.status_code == 200
    assert (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        in export_res.headers["content-type"]
    )
    assert "laporan_presensi_IF201.xlsx" in export_res.headers["content-disposition"]

    wb = load_workbook(io.BytesIO(export_res.content))
    assert set(wb.sheetnames) == {"Rekap Kehadiran", "Warning (<75%)", "Detail Sesi"}
    ws_warn = wb["Warning (<75%)"]
    # Baris 3 header, baris 4..8 berisi 5 mahasiswa warning
    exported_warn_nims = {ws_warn.cell(row=r, column=2).value for r in range(4, 9)}
    assert exported_warn_nims == {"2301003", "2301004", "2301005", "2301006", "2301008"}


# ==============================================================================
# 4. DELIVERABLE 4: AI ATTENDANCE INSIGHTS (15%)
# ==============================================================================


def test_ai_insights_from_database_detects_early_warning_and_patterns(client: TestClient):
    """Kriteria Sukses: AI memberikan early warning mahasiswa berisiko & deteksi pola."""
    meta = client.get("/attendance/meta").json()
    algo_course = next(c for c in meta["courses"] if c["code"] == "IF201")

    res = client.get(f"/attendance/ai/insights?course_id={algo_course['id']}")
    assert res.status_code == 200
    data = res.json()

    assert "5 mahasiswa berisiko" in data["early_warning_headline"]
    assert len(data["at_risk_students"]) == 5
    assert len(data["high_absence_patterns"]) >= 1
    assert data["high_absence_patterns"][0]["day"] == "Senin"
    assert data["high_absence_patterns"][0]["time_slot"] == "07:00"
    assert data["high_absence_patterns"][0]["absent_rate_percentage"] >= 40.0
    assert len(data["insights"]) > 0
    assert len(data["actions"]) > 0
    assert any("reschedule" in a["recommendation"].lower() for a in data["actions"])
    assert any("konseling" in a["recommendation"].lower() for a in data["actions"])


def test_ai_analyze_custom_json_array_endpoint(client: TestClient):
    """Menguji Step 3: input attendance_records (JSON array) -> structured JSON insights + actions."""
    sample_records = [
        {"nim": "2309001", "student_name": "Budi", "course_code": "KLS-Y", "course_name": "Kelas Y", "day": "Senin", "time": "07:00", "status": "absent"},
        {"nim": "2309001", "student_name": "Budi", "course_code": "KLS-Y", "course_name": "Kelas Y", "day": "Senin", "time": "07:00", "status": "absent"},
        {"nim": "2309001", "student_name": "Budi", "course_code": "KLS-Y", "course_name": "Kelas Y", "day": "Senin", "time": "07:00", "status": "absent"},
        {"nim": "2309001", "student_name": "Budi", "course_code": "KLS-Y", "course_name": "Kelas Y", "day": "Senin", "time": "07:00", "status": "hadir"},
        {"nim": "2309002", "student_name": "Sari", "course_code": "KLS-Y", "course_name": "Kelas Y", "day": "Senin", "time": "07:00", "status": "hadir"},
        {"nim": "2309002", "student_name": "Sari", "course_code": "KLS-Y", "course_name": "Kelas Y", "day": "Senin", "time": "07:00", "status": "hadir"},
        {"nim": "2309002", "student_name": "Sari", "course_code": "KLS-Y", "course_name": "Kelas Y", "day": "Senin", "time": "07:00", "status": "absent"},
        {"nim": "2309002", "student_name": "Sari", "course_code": "KLS-Y", "course_name": "Kelas Y", "day": "Senin", "time": "07:00", "status": "hadir"},
    ]
    res = client.post("/attendance/ai/analyze", json={"attendance_records": sample_records})
    assert res.status_code == 200
    body = res.json()

    # Budi: 1/4 = 25% -> at risk; Kelas Y 07:00: 4/8 = 50% absent rate
    assert len(body["at_risk_students"]) == 1
    assert body["at_risk_students"][0]["nim"] == "2309001"
    assert body["at_risk_students"][0]["attendance_percentage"] == 25.0
    assert body["high_absence_patterns"][0]["absent_rate_percentage"] == 50.0
    assert any("senin" in ins["summary"].lower() for ins in body["insights"])
    assert any("reschedule" in act["recommendation"].lower() for act in body["actions"])


# ==============================================================================
# 5. DELIVERABLE 5: SECURITY — QR EXPIRATION & RATE LIMITING (5%)
# ==============================================================================


def test_expired_qr_token_is_rejected(client: TestClient):
    """Kriteria Sukses: Expired QR ditolak sistem."""
    schedule_id = _get_live_schedule_id(client)
    past_time = datetime.now(timezone.utc) - timedelta(minutes=20)
    expired_token, _, _ = create_qr_jwt(
        schedule_id=schedule_id,
        session_id=999,
        jti="expired-test-jti",
        valid_minutes=15,
        now_utc=past_time,
    )

    res = client.post("/attendance/scan", json={"token": expired_token, "nim": "2301001"})
    assert res.status_code == 401
    assert "expired" in res.json()["detail"].lower() or "kadaluarsa" in res.json()["detail"].lower()


def test_tampered_qr_token_is_rejected(client: TestClient):
    res = client.post("/attendance/scan", json={"token": "invalid.jwt.tokenvalue", "nim": "2301001"})
    assert res.status_code == 401


def test_rate_limiting_blocks_spam_scan(client: TestClient):
    """Keamanan: Rate limiting memblokir spam scan dengan HTTP 429."""
    schedule_id = _get_live_schedule_id(client)
    qr_info = client.get(f"/attendance/qr/{schedule_id}/info").json()
    token = qr_info["token"]

    statuses = []
    # Kirim request melebihi batas RATE_LIMIT_MAX_REQUESTS (default 5/menit)
    for _ in range(settings.RATE_LIMIT_MAX_REQUESTS + 2):
        r = client.post("/attendance/scan", json={"token": token, "nim": "2301009"})
        statuses.append(r.status_code)

    assert 429 in statuses


def test_dashboard_health_and_mandatory_geolocation(client: TestClient, db_session):
    """Memastikan dashboard UI, endpoint health, dan validasi lokasi wajib berjalan benar."""
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    home = client.get("/")
    assert home.status_code == 200
    assert "Modul Presensi Berbasis QR Code" in home.text

    # Aktifkan require_geolocation pada jadwal live
    schedule_id = _get_live_schedule_id(client)
    sched = db_session.get(Schedule, schedule_id)
    assert sched is not None
    sched.require_geolocation = True
    db_session.commit()

    qr_info = client.get(f"/attendance/qr/{schedule_id}/info").json()
    res_no_geo = client.post(
        "/attendance/scan",
        json={"token": qr_info["token"], "nim": "2301003"},
    )
    assert res_no_geo.status_code == 400
    assert "validasi lokasi" in res_no_geo.json()["detail"].lower()
