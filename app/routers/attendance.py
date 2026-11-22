"""Endpoint API Modul Presensi (QR Code)."""

from __future__ import annotations

import io
from datetime import datetime, time, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import DAY_NAMES_ID, settings
from app.database import get_db
from app.models import Course, Enrollment, Schedule, Student
from app.schemas import (
    AIAnalyzeRequest,
    AIInsightsResponse,
    AttendanceScanRequest,
    AttendanceScanResponse,
    CourseReportResponse,
    CreateScheduleRequest,
    QRSessionInfoResponse,
    StudentReportResponse,
)
from app.security import require_lecturer_role, scan_rate_limiter
from app.services.ai_service import (
    analyze_attendance_records,
    build_attendance_dataset_from_db,
)
from app.services.attendance_service import record_attendance_scan
from app.services.qr_service import create_or_refresh_session_qr
from app.services.report_service import (
    export_course_report_to_excel,
    get_course_attendance_report,
    get_student_attendance_report,
)

router = APIRouter(prefix="/attendance", tags=["Attendance & QR Presensi"])


# --- Deliverable 1: QR Generation Service (30%) ---


@router.get(
    "/qr/{schedule_id}",
    summary="Generate QR Code Presensi (Image PNG)",
    responses={
        200: {"content": {"image/png": {}}, "description": "QR Code image berformat PNG"},
        403: {"description": "Akses ditolak untuk role non-dosen"},
        404: {"description": "Jadwal tidak ditemukan"},
    },
)
def get_attendance_qr_image(
    schedule_id: int,
    valid_minutes: int = Query(
        default=settings.QR_VALID_MINUTES,
        ge=1,
        le=60,
        description="Masa berlaku QR dalam menit (default 15 menit)",
    ),
    db: Session = Depends(get_db),
    _role: str = Depends(require_lecturer_role),
) -> Response:
    """Dosen men-generate gambar QR Code unik yang valid selama 15 menit untuk sesi kuliah."""
    result = create_or_refresh_session_qr(
        db=db,
        schedule_id=schedule_id,
        valid_minutes=valid_minutes,
    )
    headers = {
        "X-Attendance-Token": result.token,
        "X-Session-Id": str(result.session.id),
        "X-Token-Jti": result.jti,
        "X-Expires-At": result.expires_at.isoformat(),
        "X-Valid-Minutes": str(result.valid_minutes),
        "Cache-Control": "no-store",
    }
    return Response(content=result.png_bytes, media_type="image/png", headers=headers)


@router.get(
    "/qr/{schedule_id}/info",
    response_model=QRSessionInfoResponse,
    summary="Generate QR Code Presensi (JSON + Base64 PNG)",
)
def get_attendance_qr_info(
    schedule_id: int,
    valid_minutes: int = Query(default=settings.QR_VALID_MINUTES, ge=1, le=60),
    db: Session = Depends(get_db),
    _role: str = Depends(require_lecturer_role),
) -> QRSessionInfoResponse:
    """Mengembalikan metadata sesi QR, token JWT, waktu expired, dan QR PNG dalam Base64."""
    result = create_or_refresh_session_qr(
        db=db,
        schedule_id=schedule_id,
        valid_minutes=valid_minutes,
    )
    return QRSessionInfoResponse(
        schedule_id=result.schedule.id,
        session_id=result.session.id,
        course_code=result.course.code,
        course_name=result.course.name,
        lecturer_name=result.schedule.lecturer_name,
        day_name=result.day_name,
        start_time=result.schedule.start_time.strftime("%H:%M"),
        end_time=result.schedule.end_time.strftime("%H:%M"),
        room=result.schedule.room,
        meeting_number=result.session.meeting_number,
        jti=result.jti,
        token=result.token,
        valid_minutes=result.valid_minutes,
        generated_at=result.generated_at,
        expires_at=result.expires_at,
        qr_image_base64=result.qr_base64,
    )


# --- Deliverable 2 & 5: Attendance Recording (30%) + Rate Limiting Security (5%) ---


@router.post(
    "/scan",
    response_model=AttendanceScanResponse,
    summary="Mahasiswa Scan QR Code Presensi",
)
def scan_attendance_qr(
    payload: AttendanceScanRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> AttendanceScanResponse:
    """Validasi scan QR oleh mahasiswa dengan rate limiting, JWT check, jadwal, enrollment, lokasi & anti-duplikat."""
    client_ip = request.client.host if request.client else "unknown"
    ip_allowed, ip_retry = scan_rate_limiter.check(f"ip:{client_ip}")
    if not ip_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Terlalu banyak percobaan scan dari perangkat ini. "
                f"Coba lagi dalam {ip_retry} detik."
            ),
            headers={"Retry-After": str(ip_retry)},
        )

    nim_allowed, nim_retry = scan_rate_limiter.check(f"nim:{payload.nim}")
    if not nim_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Terlalu banyak percobaan scan untuk NIM {payload.nim}. "
                f"Coba lagi dalam {nim_retry} detik."
            ),
            headers={"Retry-After": str(nim_retry)},
        )

    return record_attendance_scan(db=db, payload=payload)


# --- Deliverable 3: Attendance Report & Excel Export (20%) ---


@router.get(
    "/report/student/{nim}",
    response_model=StudentReportResponse,
    summary="Laporan Persentase Kehadiran per Mahasiswa",
)
def report_by_student(
    nim: str,
    db: Session = Depends(get_db),
) -> StudentReportResponse:
    return get_student_attendance_report(db=db, nim=nim)


@router.get(
    "/report/course/{course_id}",
    response_model=CourseReportResponse,
    summary="Laporan Kehadiran per Mata Kuliah & Warning (<75%)",
)
def report_by_course(
    course_id: int,
    db: Session = Depends(get_db),
) -> CourseReportResponse:
    return get_course_attendance_report(db=db, course_id=course_id)


@router.get(
    "/report/course/{course_id}/export",
    summary="Export Laporan Presensi Mata Kuliah ke Excel (.xlsx)",
)
def export_course_report_excel(
    course_id: int,
    db: Session = Depends(get_db),
    _role: str = Depends(require_lecturer_role),
) -> StreamingResponse:
    excel_bytes, filename = export_course_report_to_excel(db=db, course_id=course_id)
    return StreamingResponse(
        io.BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# --- Deliverable 4: AI Attendance Insights (15%) ---


@router.get(
    "/ai/insights",
    response_model=AIInsightsResponse,
    summary="AI Attendance Insights dari Data Presensi Database",
)
def get_ai_attendance_insights(
    course_id: Optional[int] = Query(
        default=None, description="Opsional: filter analisis untuk satu course_id"
    ),
    db: Session = Depends(get_db),
) -> AIInsightsResponse:
    dataset = build_attendance_dataset_from_db(db=db, course_id=course_id)
    return analyze_attendance_records(dataset)


@router.post(
    "/ai/analyze",
    response_model=AIInsightsResponse,
    summary="AI Attendance Analyzer dari Input JSON Array (Step 3)",
)
def analyze_custom_attendance_records(
    payload: AIAnalyzeRequest,
) -> AIInsightsResponse:
    return analyze_attendance_records(payload.attendance_records)


# --- Helper Metadata & Pengelolaan Jadwal (untuk Dashboard & Demo) ---


@router.get("/meta", summary="Daftar Mata Kuliah, Jadwal, dan Mahasiswa")
def get_metadata(db: Session = Depends(get_db)) -> dict:
    local_now = settings.now_local()

    courses = db.execute(select(Course).order_by(Course.code)).scalars().all()
    schedules = (
        db.execute(
            select(Schedule, Course)
            .join(Course, Course.id == Schedule.course_id)
            .order_by(Schedule.id)
        )
        .all()
    )
    students = db.execute(select(Student).order_by(Student.nim)).scalars().all()
    enrollments = db.execute(select(Enrollment)).scalars().all()

    enrolled_by_nim: dict[str, list[int]] = {}
    for enr in enrollments:
        enrolled_by_nim.setdefault(enr.nim, []).append(enr.course_id)

    schedule_list = []
    for sched, course in schedules:
        is_today = sched.day_of_week == local_now.weekday()
        sched_start = datetime.combine(local_now.date(), sched.start_time, tzinfo=settings.tz)
        elapsed_min = (local_now - sched_start).total_seconds() / 60.0
        in_scan_window = (
            is_today and -5.0 <= elapsed_min <= float(settings.TERLAMBAT_MAX_MINUTES)
        )
        schedule_list.append(
            {
                "id": sched.id,
                "course_id": course.id,
                "course_code": course.code,
                "course_name": course.name,
                "lecturer_name": sched.lecturer_name,
                "day_of_week": sched.day_of_week,
                "day_name": DAY_NAMES_ID.get(sched.day_of_week, str(sched.day_of_week)),
                "start_time": sched.start_time.strftime("%H:%M"),
                "end_time": sched.end_time.strftime("%H:%M"),
                "room": sched.room,
                "latitude": sched.latitude,
                "longitude": sched.longitude,
                "radius_meters": sched.radius_meters,
                "require_geolocation": sched.require_geolocation,
                "is_today": is_today,
                "in_scan_window": in_scan_window,
            }
        )

    return {
        "server_time_local": local_now.isoformat(),
        "today_name": DAY_NAMES_ID.get(local_now.weekday(), ""),
        "courses": [
            {"id": c.id, "code": c.code, "name": c.name, "credits": c.credits}
            for c in courses
        ],
        "schedules": schedule_list,
        "students": [
            {
                "nim": s.nim,
                "name": s.name,
                "email": s.email,
                "enrolled_course_ids": enrolled_by_nim.get(s.nim, []),
            }
            for s in students
        ],
    }


@router.post(
    "/schedules",
    status_code=status.HTTP_201_CREATED,
    summary="Tambah Jadwal Kuliah Baru",
)
def create_schedule(
    payload: CreateScheduleRequest,
    db: Session = Depends(get_db),
    _role: str = Depends(require_lecturer_role),
) -> dict:
    course = db.get(Course, payload.course_id)
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Mata kuliah ID {payload.course_id} tidak ditemukan.",
        )

    sh, sm = map(int, payload.start_time.split(":"))
    eh, em = map(int, payload.end_time.split(":"))

    schedule = Schedule(
        course_id=payload.course_id,
        lecturer_id=payload.lecturer_id,
        lecturer_name=payload.lecturer_name,
        day_of_week=payload.day_of_week,
        start_time=time(sh, sm),
        end_time=time(eh, em),
        room=payload.room,
        latitude=payload.latitude,
        longitude=payload.longitude,
        radius_meters=payload.radius_meters,
        require_geolocation=payload.require_geolocation,
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)

    return {
        "id": schedule.id,
        "course_id": schedule.course_id,
        "course_code": course.code,
        "day_name": DAY_NAMES_ID.get(schedule.day_of_week, ""),
        "start_time": schedule.start_time.strftime("%H:%M"),
        "end_time": schedule.end_time.strftime("%H:%M"),
        "room": schedule.room,
    }


@router.post(
    "/schedules/demo-now",
    summary="Siapkan Jadwal Demo Aktif untuk Jam Saat Ini",
)
def ensure_live_demo_schedule(
    course_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _role: str = Depends(require_lecturer_role),
) -> dict:
    """Menyelaraskan jadwal demo (IF203) agar aktif tepat pada hari & jam sekarang."""
    local_now = settings.now_local()
    target_course = (
        db.get(Course, course_id)
        if course_id
        else db.execute(select(Course).where(Course.code == "IF203")).scalar_one_or_none()
    )
    if not target_course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mata kuliah target tidak ditemukan.",
        )

    start_dt = local_now.replace(second=0, microsecond=0)
    end_dt = start_dt + timedelta(hours=2)
    if end_dt.date() != start_dt.date():
        end_t = time(23, 59)
    else:
        end_t = end_dt.time()

    demo_sched = db.execute(
        select(Schedule).where(
            Schedule.course_id == target_course.id,
            Schedule.room == "Lab Komputer 2 (Live Demo)",
        )
    ).scalar_one_or_none()

    if demo_sched is None:
        demo_sched = Schedule(
            course_id=target_course.id,
            lecturer_id="DSN003",
            lecturer_name="Ir. Budi Santoso, M.T.",
            day_of_week=local_now.weekday(),
            start_time=start_dt.time(),
            end_time=end_t,
            room="Lab Komputer 2 (Live Demo)",
            latitude=-6.200000,
            longitude=106.816666,
            radius_meters=150.0,
            require_geolocation=False,
        )
        db.add(demo_sched)
    else:
        demo_sched.day_of_week = local_now.weekday()
        demo_sched.start_time = start_dt.time()
        demo_sched.end_time = end_t

    db.commit()
    db.refresh(demo_sched)

    return {
        "schedule_id": demo_sched.id,
        "course_code": target_course.code,
        "course_name": target_course.name,
        "day_name": DAY_NAMES_ID.get(demo_sched.day_of_week, ""),
        "start_time": demo_sched.start_time.strftime("%H:%M"),
        "end_time": demo_sched.end_time.strftime("%H:%M"),
        "room": demo_sched.room,
        "message": "Jadwal live demo siap digunakan untuk generate QR dan scan presensi sekarang.",
    }
