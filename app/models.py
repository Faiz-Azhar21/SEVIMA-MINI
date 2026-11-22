"""Model database ORM untuk Modul Presensi QR Code."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Course(Base):
    """Tabel mata kuliah."""

    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    credits: Mapped[int] = mapped_column(Integer, default=3, nullable=False)

    enrollments: Mapped[list["Enrollment"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )
    schedules: Mapped[list["Schedule"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )


class Student(Base):
    """Tabel mahasiswa."""

    __tablename__ = "students"

    nim: Mapped[str] = mapped_column(String(30), primary_key=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)

    enrollments: Mapped[list["Enrollment"]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )
    attendance_records: Mapped[list["AttendanceRecord"]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )


class Enrollment(Base):
    """Tabel pendaftaran (KRS) mahasiswa pada mata kuliah."""

    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("nim", "course_id", name="uq_enrollment_nim_course"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nim: Mapped[str] = mapped_column(ForeignKey("students.nim"), nullable=False, index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False, index=True)

    student: Mapped["Student"] = relationship(back_populates="enrollments")
    course: Mapped["Course"] = relationship(back_populates="enrollments")


class Schedule(Base):
    """Tabel jadwal perkuliahan mingguan."""

    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False, index=True)
    lecturer_id: Mapped[str] = mapped_column(String(30), nullable=False)
    lecturer_name: Mapped[str] = mapped_column(String(150), nullable=False)
    # 0 = Senin, 1 = Selasa, ..., 6 = Minggu
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    room: Mapped[str] = mapped_column(String(80), nullable=False)

    # Opsional: validasi lokasi (geolocation)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    radius_meters: Mapped[float] = mapped_column(Float, default=100.0, nullable=False)
    require_geolocation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    course: Mapped["Course"] = relationship(back_populates="schedules")
    sessions: Mapped[list["AttendanceSession"]] = relationship(
        back_populates="schedule", cascade="all, delete-orphan"
    )


class AttendanceSession(Base):
    """Tabel sesi presensi per pertemuan kuliah (menyimpan token JTI unik anti-replay)."""

    __tablename__ = "attendance_sessions"
    __table_args__ = (
        UniqueConstraint("schedule_id", "session_date", name="uq_session_schedule_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    schedule_id: Mapped[int] = mapped_column(ForeignKey("schedules.id"), nullable=False, index=True)
    session_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    meeting_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Token unik aktif untuk mencegah replay attack
    active_jti: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    schedule: Mapped["Schedule"] = relationship(back_populates="sessions")
    records: Mapped[list["AttendanceRecord"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class AttendanceRecord(Base):
    """Tabel catatan presensi hasil scan mahasiswa."""

    __tablename__ = "attendance_records"
    __table_args__ = (UniqueConstraint("session_id", "nim", name="uq_record_session_nim"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("attendance_sessions.id"), nullable=False, index=True
    )
    schedule_id: Mapped[int] = mapped_column(ForeignKey("schedules.id"), nullable=False, index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), nullable=False, index=True)
    nim: Mapped[str] = mapped_column(ForeignKey("students.nim"), nullable=False, index=True)

    # Status: "hadir" atau "terlambat"
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    scanned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now, nullable=False)
    token_jti: Mapped[str] = mapped_column(String(64), nullable=False)

    # Opsional: jejak lokasi saat scan
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    distance_meters: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    session: Mapped["AttendanceSession"] = relationship(back_populates="records")
    student: Mapped["Student"] = relationship(back_populates="attendance_records")
