"""Service 1: QR Generation Service (30%).

Menangani pembuatan token JWT unik per sesi (anti replay attack) dan rendering QR Code PNG.
"""

from __future__ import annotations

import base64
import io
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import qrcode
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import DAY_NAMES_ID, settings
from app.models import AttendanceSession, Course, Schedule
from app.security import create_qr_jwt


@dataclass
class GeneratedQRResult:
    schedule: Schedule
    course: Course
    session: AttendanceSession
    token: str
    jti: str
    valid_minutes: int
    generated_at: datetime
    expires_at: datetime
    png_bytes: bytes

    @property
    def qr_base64(self) -> str:
        return base64.b64encode(self.png_bytes).decode("ascii")

    @property
    def day_name(self) -> str:
        return DAY_NAMES_ID.get(self.schedule.day_of_week, str(self.schedule.day_of_week))


def generate_attendance_qr(
    schedule_id: int,
    valid_minutes: int = 15,
    session_id: int = 0,
    jti: str | None = None,
    now_utc: datetime | None = None,
):
    """Implementasi generator QR code untuk presensi berbasis JWT.

    Menghasilkan objek gambar QR (PIL Image) dan string token JWT dengan payload:
    schedule_id, session_id, jti (token unik per sesi), iat, dan exp.
    """
    unique_jti = jti or uuid.uuid4().hex
    token, _, _ = create_qr_jwt(
        schedule_id=schedule_id,
        session_id=session_id,
        jti=unique_jti,
        valid_minutes=valid_minutes,
        now_utc=now_utc,
    )

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=3,
    )
    qr.add_data(token)
    qr.make(fit=True)
    qr_image = qr.make_image(fill_color="black", back_color="white")
    return qr_image, token


def qr_image_to_png_bytes(qr_image) -> bytes:
    """Mengonversi objek gambar QR ke bytes format PNG."""
    buffer = io.BytesIO()
    qr_image.save(buffer, format="PNG")
    return buffer.getvalue()


def create_or_refresh_session_qr(
    db: Session,
    schedule_id: int,
    valid_minutes: int | None = None,
    now_local: datetime | None = None,
) -> GeneratedQRResult:
    """Membuat atau memperbarui sesi presensi hari ini dengan token JTI unik.

    Setiap kali dosen men-generate QR baru pada jadwal yang sama di hari yang sama,
    `active_jti` dirotasi sehingga token lama otomatis tidak berlaku (anti replay attack).
    """
    duration = valid_minutes if valid_minutes is not None else settings.QR_VALID_MINUTES
    if duration < 1 or duration > 60:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Durasi validitas QR harus antara 1 sampai 60 menit.",
        )

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
            detail=f"Mata kuliah untuk jadwal ID {schedule_id} tidak ditemukan.",
        )

    local_now = now_local or settings.now_local()
    if local_now.tzinfo is None:
        local_now = local_now.replace(tzinfo=settings.tz)
    utc_now = local_now.astimezone(timezone.utc)
    today = local_now.date()

    new_jti = uuid.uuid4().hex
    expires_at = utc_now + timedelta(minutes=duration)

    session = db.execute(
        select(AttendanceSession).where(
            AttendanceSession.schedule_id == schedule_id,
            AttendanceSession.session_date == today,
        )
    ).scalar_one_or_none()

    if session is None:
        existing_count = (
            db.execute(
                select(func.count(AttendanceSession.id)).where(
                    AttendanceSession.schedule_id == schedule_id
                )
            ).scalar_one()
            or 0
        )
        session = AttendanceSession(
            schedule_id=schedule_id,
            session_date=today,
            meeting_number=existing_count + 1,
            active_jti=new_jti,
            opened_at=utc_now,
            expires_at=expires_at,
            is_active=True,
        )
        db.add(session)
        db.flush()
    else:
        # Rotasi JTI mencegah replay attack dari QR yang lama
        session.active_jti = new_jti
        session.expires_at = expires_at
        session.is_active = True

    qr_image, token = generate_attendance_qr(
        schedule_id=schedule_id,
        valid_minutes=duration,
        session_id=session.id,
        jti=new_jti,
        now_utc=utc_now,
    )
    png_bytes = qr_image_to_png_bytes(qr_image)

    db.commit()
    db.refresh(session)

    return GeneratedQRResult(
        schedule=schedule,
        course=course,
        session=session,
        token=token,
        jti=new_jti,
        valid_minutes=duration,
        generated_at=utc_now,
        expires_at=expires_at,
        png_bytes=png_bytes,
    )
