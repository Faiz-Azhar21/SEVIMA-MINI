"""Service 2: Attendance Recording & Scan Validation (30%).

Pipeline validasi:
1. Decode JWT -> ekstrak schedule_id, session_id, jti & cek exp
2. Anti-replay -> pastikan jti sesuai dengan sesi aktif di database
3. Query schedule -> pastikan hari ini ada jadwal kuliah & dalam window waktu valid
4. Cek enrollment -> pastikan mahasiswa terdaftar di MK ini
5. Geolocation validation (opsional) -> validasi jarak mahasiswa dari ruang kelas
6. Check duplicate -> pastikan belum scan pada sesi ini
7. Calculate status -> Hadir (<= 15 menit), Terlambat (> 15 s.d. 30 menit)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import DAY_NAMES_ID, settings
from app.models import (
    AttendanceRecord,
    AttendanceSession,
    Course,
    Enrollment,
    Schedule,
    Student,
)
from app.schemas import AttendanceScanDetail, AttendanceScanRequest, AttendanceScanResponse
from app.security import TokenValidationError, decode_qr_jwt, haversine_distance_meters


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def record_attendance_scan(
    db: Session,
    payload: AttendanceScanRequest,
    now_local: datetime | None = None,
) -> AttendanceScanResponse:
    """Memvalidasi scan QR mahasiswa dan menyimpan catatan presensi."""
    local_now = now_local or settings.now_local()
    if local_now.tzinfo is None:
        local_now = local_now.replace(tzinfo=settings.tz)
    utc_now = local_now.astimezone(timezone.utc)

    # 1. Decode JWT -> extract schedule_id & check exp
    try:
        claims = decode_qr_jwt(
            payload.token,
            now_utc=utc_now if now_local is not None else None,
        )
    except TokenValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=exc.message,
        ) from exc

    schedule_id = claims.get("schedule_id")
    session_id = claims.get("session_id")
    token_jti = claims.get("jti")

    if not isinstance(schedule_id, int):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Payload token QR tidak mengandung schedule_id yang valid.",
        )

    # 2. Query schedule & verifikasi anti-replay terhadap sesi aktif
    schedule = db.get(Schedule, schedule_id)
    if not schedule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Jadwal kuliah dengan ID {schedule_id} tidak ditemukan.",
        )

    course = db.get(Course, schedule.course_id)
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mata kuliah terkait jadwal ini tidak ditemukan.",
        )

    session: AttendanceSession | None = None
    if isinstance(session_id, int) and session_id > 0:
        session = db.get(AttendanceSession, session_id)
    else:
        session = db.execute(
            select(AttendanceSession).where(
                AttendanceSession.schedule_id == schedule_id,
                AttendanceSession.session_date == local_now.date(),
            )
        ).scalar_one_or_none()

    if not session or session.schedule_id != schedule_id or not session.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesi presensi tidak aktif atau tidak ditemukan.",
        )

    if token_jti and session.active_jti != token_jti:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token QR sudah tidak berlaku karena telah diganti (anti-replay protection).",
        )

    if utc_now > _ensure_utc(session.expires_at):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="QR code sudah melewati batas waktu valid sesi (expired).",
        )

    # 3. Validasi jadwal: apakah hari ini ada kuliah & berada dalam window waktu valid?
    if local_now.weekday() != schedule.day_of_week:
        scheduled_day = DAY_NAMES_ID.get(schedule.day_of_week, str(schedule.day_of_week))
        today_name = DAY_NAMES_ID.get(local_now.weekday(), str(local_now.weekday()))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Tidak ada jadwal kuliah {course.code} hari ini ({today_name}). "
                f"Jadwal terdaftar pada hari {scheduled_day}."
            ),
        )

    scheduled_start = datetime.combine(
        local_now.date(), schedule.start_time, tzinfo=settings.tz
    )
    scheduled_end = datetime.combine(
        local_now.date(), schedule.end_time, tzinfo=settings.tz
    )
    if scheduled_end <= scheduled_start:
        scheduled_end += timedelta(days=1)

    # Izinkan toleransi scan 5 menit sebelum jam mulai jika dosen membuka kelas sedikit lebih awal
    earliest_allowed = scheduled_start - timedelta(minutes=5)
    if local_now < earliest_allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Sesi kuliah {course.code} belum dimulai "
                f"(mulai pukul {schedule.start_time.strftime('%H:%M')})."
            ),
        )

    if local_now > scheduled_end:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Jadwal kuliah {course.code} hari ini sudah berakhir "
                f"(berakhir pukul {schedule.end_time.strftime('%H:%M')})."
            ),
        )

    elapsed_minutes = max(0.0, (local_now - scheduled_start).total_seconds() / 60.0)
    if elapsed_minutes > settings.TERLAMBAT_MAX_MINUTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Waktu presensi sudah ditutup (sudah lewat {elapsed_minutes:.1f} menit; "
                f"batas maksimal {settings.TERLAMBAT_MAX_MINUTES} menit)."
            ),
        )

    # 4. Cek mahasiswa & enrollment: apakah mahasiswa terdaftar di MK ini?
    student = db.get(Student, payload.nim)
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Mahasiswa dengan NIM '{payload.nim}' tidak ditemukan di sistem.",
        )

    enrollment = db.execute(
        select(Enrollment).where(
            Enrollment.nim == payload.nim,
            Enrollment.course_id == schedule.course_id,
        )
    ).scalar_one_or_none()

    if not enrollment:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Mahasiswa {student.name} ({payload.nim}) tidak terdaftar pada mata kuliah "
                f"{course.code} - {course.name}. Tidak dapat scan QR kelas orang lain."
            ),
        )

    # 5. Geolocation validation (opsional — wajib jika schedule.require_geolocation=True)
    distance_meters: float | None = None
    has_student_geo = payload.latitude is not None and payload.longitude is not None
    has_room_geo = schedule.latitude is not None and schedule.longitude is not None

    if schedule.require_geolocation and not has_student_geo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Jadwal ini mewajibkan validasi lokasi (latitude & longitude harus dikirim).",
        )

    if has_student_geo and has_room_geo:
        distance_meters = haversine_distance_meters(
            payload.latitude,  # type: ignore[arg-type]
            payload.longitude,  # type: ignore[arg-type]
            schedule.latitude,  # type: ignore[arg-type]
            schedule.longitude,  # type: ignore[arg-type]
        )
        if distance_meters > schedule.radius_meters:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Lokasi Anda berada di luar radius ruang kuliah {schedule.room} "
                    f"(jarak: {distance_meters:.1f} m, maksimal: {schedule.radius_meters:.0f} m)."
                ),
            )

    # 6. Check duplicate: apakah mahasiswa sudah scan sebelumnya pada sesi ini?
    existing_record = db.execute(
        select(AttendanceRecord).where(
            AttendanceRecord.session_id == session.id,
            AttendanceRecord.nim == payload.nim,
        )
    ).scalar_one_or_none()

    if existing_record:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Mahasiswa {student.name} ({payload.nim}) sudah melakukan presensi "
                f"pada sesi ini dengan status '{existing_record.status}'."
            ),
        )

    # 7. Calculate status: Hadir (<= 15 menit) atau Terlambat (15 - 30 menit)
    attendance_status = (
        "hadir" if elapsed_minutes <= settings.HADIR_WINDOW_MINUTES else "terlambat"
    )

    record = AttendanceRecord(
        session_id=session.id,
        schedule_id=schedule.id,
        course_id=course.id,
        nim=student.nim,
        status=attendance_status,
        scanned_at=utc_now,
        token_jti=token_jti or session.active_jti,
        latitude=payload.latitude,
        longitude=payload.longitude,
        distance_meters=distance_meters,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    status_label = "HADIR" if attendance_status == "hadir" else "TERLAMBAT"
    message = (
        f"Presensi {student.name} ({student.nim}) pada mata kuliah "
        f"{course.code} - {course.name} berhasil dicatat sebagai {status_label}."
    )

    return AttendanceScanResponse(
        success=True,
        status=attendance_status,  # type: ignore[arg-type]
        message=message,
        data=AttendanceScanDetail(
            record_id=record.id,
            session_id=session.id,
            schedule_id=schedule.id,
            course_code=course.code,
            course_name=course.name,
            nim=student.nim,
            student_name=student.name,
            status=attendance_status,  # type: ignore[arg-type]
            scanned_at=utc_now,
            elapsed_minutes=round(elapsed_minutes, 2),
            distance_meters=distance_meters,
        ),
    )
