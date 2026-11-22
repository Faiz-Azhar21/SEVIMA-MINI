"""Skema Pydantic untuk validasi request & response API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# --- QR Generation ---


class QRSessionInfoResponse(BaseModel):
    schedule_id: int
    session_id: int
    course_code: str
    course_name: str
    lecturer_name: str
    day_name: str
    start_time: str
    end_time: str
    room: str
    meeting_number: int
    jti: str
    token: str
    valid_minutes: int
    generated_at: datetime
    expires_at: datetime
    qr_image_base64: str


# --- Scan Attendance ---


class AttendanceScanRequest(BaseModel):
    token: str = Field(..., min_length=10, description="JWT token hasil scan QR Code")
    nim: str = Field(..., min_length=3, max_length=30, description="NIM mahasiswa")
    latitude: Optional[float] = Field(None, ge=-90, le=90, description="Opsional: koordinat lintang")
    longitude: Optional[float] = Field(None, ge=-180, le=180, description="Opsional: koordinat bujur")


class AttendanceScanDetail(BaseModel):
    record_id: int
    session_id: int
    schedule_id: int
    course_code: str
    course_name: str
    nim: str
    student_name: str
    status: Literal["hadir", "terlambat"]
    scanned_at: datetime
    elapsed_minutes: float
    distance_meters: Optional[float] = None


class AttendanceScanResponse(BaseModel):
    success: bool
    status: Literal["hadir", "terlambat"]
    message: str
    data: AttendanceScanDetail


# --- Attendance Reports ---


class StudentCourseAttendanceItem(BaseModel):
    course_id: int
    course_code: str
    course_name: str
    total_sessions: int
    hadir: int
    terlambat: int
    absent: int
    attended_sessions: int
    attendance_percentage: float
    warning: bool


class StudentReportResponse(BaseModel):
    nim: str
    student_name: str
    overall_attendance_percentage: float
    warning_courses_count: int
    courses: list[StudentCourseAttendanceItem]


class CourseStudentAttendanceItem(BaseModel):
    nim: str
    student_name: str
    hadir: int
    terlambat: int
    absent: int
    total_sessions: int
    attendance_percentage: float
    warning: bool


class CourseReportResponse(BaseModel):
    course_id: int
    course_code: str
    course_name: str
    total_sessions: int
    total_students: int
    average_attendance_percentage: float
    warning_threshold: float
    warning_count: int
    warning_students: list[CourseStudentAttendanceItem]
    students: list[CourseStudentAttendanceItem]


# --- AI Attendance Insights ---


class RawAttendanceRecordInput(BaseModel):
    nim: str
    student_name: Optional[str] = None
    course_code: Optional[str] = "UMUM"
    course_name: Optional[str] = "Mata Kuliah"
    day: Optional[str] = None
    time: Optional[str] = None
    date: Optional[str] = None
    status: Literal["hadir", "terlambat", "absent", "alpha", "tidak_hadir"]


class AIAnalyzeRequest(BaseModel):
    attendance_records: list[RawAttendanceRecordInput] = Field(
        ..., min_length=1, description="JSON array data riwayat presensi"
    )


class StudentRiskSummary(BaseModel):
    nim: str
    student_name: str
    course_code: Optional[str] = None
    total_sessions: int
    attended: int
    absent: int
    terlambat: int
    attendance_percentage: float
    risk_level: Literal["CRITICAL", "HIGH", "WARNING"]


class TimeSlotPattern(BaseModel):
    course_code: str
    course_name: str
    day: str
    time_slot: str
    total_records: int
    absent_count: int
    absent_rate_percentage: float


class AIInsightItem(BaseModel):
    category: Literal["early_warning", "student_pattern", "schedule_pattern", "lateness_trend"]
    severity: Literal["high", "medium", "low"]
    summary: str
    metrics: dict[str, Any] = Field(default_factory=dict)


class AIActionItem(BaseModel):
    priority: Literal["high", "medium", "low"]
    target_type: Literal["student", "course_schedule", "class"]
    target: str
    recommendation: str
    reason: str


class AIInsightsResponse(BaseModel):
    analysis_mode: Literal["statistical_ai_engine", "llm_hybrid"]
    generated_at: datetime
    early_warning_headline: str
    summary: dict[str, Any]
    student_percentages: list[dict[str, Any]]
    at_risk_students: list[StudentRiskSummary]
    high_absence_patterns: list[TimeSlotPattern]
    insights: list[AIInsightItem]
    actions: list[AIActionItem]


# --- Schedule Creation (untuk demo/pengelolaan jadwal) ---


class CreateScheduleRequest(BaseModel):
    course_id: int
    lecturer_id: str = "DSN001"
    lecturer_name: str = "Dr. Andi Pratama, M.Kom"
    day_of_week: int = Field(..., ge=0, le=6, description="0=Senin .. 6=Minggu")
    start_time: str = Field(..., pattern=r"^\d{2}:\d{2}$", description="Format HH:MM")
    end_time: str = Field(..., pattern=r"^\d{2}:\d{2}$", description="Format HH:MM")
    room: str = "Ruang 301"
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    radius_meters: float = Field(100.0, gt=0)
    require_geolocation: bool = False
