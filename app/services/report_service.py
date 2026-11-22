"""Service 3: Attendance Report & Excel Export (20%).

Menyediakan:
- Rekap persentase kehadiran per mahasiswa untuk setiap mata kuliah
- Rekap per mata kuliah beserta daftar mahasiswa berisiko (<75% warning)
- Export laporan presensi ke Excel (.xlsx) untuk dosen menggunakan openpyxl
"""

from __future__ import annotations

import io
from collections import defaultdict

from fastapi import HTTPException, status
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
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
from app.schemas import (
    CourseReportResponse,
    CourseStudentAttendanceItem,
    StudentCourseAttendanceItem,
    StudentReportResponse,
)


def _calc_percentage(attended: int, total_sessions: int) -> float:
    if total_sessions <= 0:
        return 100.0
    return round((attended / total_sessions) * 100.0, 2)


def get_student_attendance_report(db: Session, nim: str) -> StudentReportResponse:
    """Menghitung persentase kehadiran per mata kuliah untuk seorang mahasiswa."""
    student = db.get(Student, nim)
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Mahasiswa dengan NIM '{nim}' tidak ditemukan.",
        )

    enrolled_courses = (
        db.execute(
            select(Course)
            .join(Enrollment, Enrollment.course_id == Course.id)
            .where(Enrollment.nim == nim)
            .order_by(Course.code)
        )
        .scalars()
        .all()
    )

    course_items: list[StudentCourseAttendanceItem] = []
    total_attended_all = 0
    total_sessions_all = 0

    for course in enrolled_courses:
        sessions = (
            db.execute(
                select(AttendanceSession)
                .join(Schedule, Schedule.id == AttendanceSession.schedule_id)
                .where(Schedule.course_id == course.id)
            )
            .scalars()
            .all()
        )
        session_ids = [s.id for s in sessions]
        total_sessions = len(session_ids)

        hadir = 0
        terlambat = 0
        if session_ids:
            records = (
                db.execute(
                    select(AttendanceRecord).where(
                        AttendanceRecord.nim == nim,
                        AttendanceRecord.session_id.in_(session_ids),
                    )
                )
                .scalars()
                .all()
            )
            for rec in records:
                if rec.status == "hadir":
                    hadir += 1
                elif rec.status == "terlambat":
                    terlambat += 1

        attended = hadir + terlambat
        absent = max(0, total_sessions - attended)
        pct = _calc_percentage(attended, total_sessions)
        warning = total_sessions > 0 and pct < settings.ATTENDANCE_WARNING_THRESHOLD

        total_attended_all += attended
        total_sessions_all += total_sessions

        course_items.append(
            StudentCourseAttendanceItem(
                course_id=course.id,
                course_code=course.code,
                course_name=course.name,
                total_sessions=total_sessions,
                hadir=hadir,
                terlambat=terlambat,
                absent=absent,
                attended_sessions=attended,
                attendance_percentage=pct,
                warning=warning,
            )
        )

    overall_pct = _calc_percentage(total_attended_all, total_sessions_all)
    warning_courses = sum(1 for item in course_items if item.warning)

    return StudentReportResponse(
        nim=student.nim,
        student_name=student.name,
        overall_attendance_percentage=overall_pct,
        warning_courses_count=warning_courses,
        courses=course_items,
    )


def get_course_attendance_report(db: Session, course_id: int) -> CourseReportResponse:
    """Menyusun laporan presensi per mata kuliah dan daftar mahasiswa <75%."""
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Mata kuliah dengan ID {course_id} tidak ditemukan.",
        )

    sessions = (
        db.execute(
            select(AttendanceSession)
            .join(Schedule, Schedule.id == AttendanceSession.schedule_id)
            .where(Schedule.course_id == course_id)
            .order_by(AttendanceSession.session_date, AttendanceSession.meeting_number)
        )
        .scalars()
        .all()
    )
    session_ids = [s.id for s in sessions]
    total_sessions = len(session_ids)

    enrolled_students = (
        db.execute(
            select(Student)
            .join(Enrollment, Enrollment.nim == Student.nim)
            .where(Enrollment.course_id == course_id)
            .order_by(Student.nim)
        )
        .scalars()
        .all()
    )

    records_by_nim: dict[str, list[AttendanceRecord]] = defaultdict(list)
    if session_ids:
        all_records = (
            db.execute(
                select(AttendanceRecord).where(AttendanceRecord.session_id.in_(session_ids))
            )
            .scalars()
            .all()
        )
        for rec in all_records:
            records_by_nim[rec.nim].append(rec)

    student_items: list[CourseStudentAttendanceItem] = []
    for student in enrolled_students:
        recs = records_by_nim.get(student.nim, [])
        hadir = sum(1 for r in recs if r.status == "hadir")
        terlambat = sum(1 for r in recs if r.status == "terlambat")
        attended = hadir + terlambat
        absent = max(0, total_sessions - attended)
        pct = _calc_percentage(attended, total_sessions)
        warning = total_sessions > 0 and pct < settings.ATTENDANCE_WARNING_THRESHOLD

        student_items.append(
            CourseStudentAttendanceItem(
                nim=student.nim,
                student_name=student.name,
                hadir=hadir,
                terlambat=terlambat,
                absent=absent,
                total_sessions=total_sessions,
                attendance_percentage=pct,
                warning=warning,
            )
        )

    warning_students = sorted(
        [s for s in student_items if s.warning],
        key=lambda item: item.attendance_percentage,
    )
    avg_pct = (
        round(
            sum(s.attendance_percentage for s in student_items) / len(student_items), 2
        )
        if student_items
        else 0.0
    )

    return CourseReportResponse(
        course_id=course.id,
        course_code=course.code,
        course_name=course.name,
        total_sessions=total_sessions,
        total_students=len(student_items),
        average_attendance_percentage=avg_pct,
        warning_threshold=settings.ATTENDANCE_WARNING_THRESHOLD,
        warning_count=len(warning_students),
        warning_students=warning_students,
        students=student_items,
    )


def _auto_fit_columns(ws) -> None:
    for col_idx, column_cells in enumerate(ws.columns, start=1):
        max_len = 0
        for cell in column_cells:
            val = "" if cell.value is None else str(cell.value)
            max_len = max(max_len, len(val))
        ws.column_dimensions[get_column_letter(col_idx)].width = min(max(max_len + 4, 12), 45)


def export_course_report_to_excel(db: Session, course_id: int) -> tuple[bytes, str]:
    """Menghasilkan file Excel (.xlsx) laporan presensi lengkap untuk dosen."""
    report = get_course_attendance_report(db, course_id)

    wb = Workbook()

    # Styling standar profesional
    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True, size=11)
    title_font = Font(bold=True, size=14, color="1F4E78")
    subtitle_font = Font(italic=True, size=10, color="555555")
    warn_fill = PatternFill(start_color="FCE4D6", end_color="FCE4D6", fill_type="solid")
    warn_font = Font(color="C00000", bold=True)
    ok_fill = PatternFill(start_color="E2EFDA", end_color="E2EFDA", fill_type="solid")
    ok_font = Font(color="375623", bold=True)
    thin_border = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9"),
    )

    # --- Sheet 1: Rekap Kehadiran ---
    ws1 = wb.active
    ws1.title = "Rekap Kehadiran"
    ws1["A1"] = f"LAPORAN PRESENSI - {report.course_code} {report.course_name}"
    ws1["A1"].font = title_font
    ws1["A2"] = (
        f"Total Sesi: {report.total_sessions} | Total Mahasiswa: {report.total_students} | "
        f"Rata-rata Kehadiran: {report.average_attendance_percentage:.2f}% | "
        f"Warning (<{report.warning_threshold:.0f}%): {report.warning_count} mahasiswa"
    )
    ws1["A2"].font = subtitle_font

    headers = [
        "No",
        "NIM",
        "Nama Mahasiswa",
        "Hadir",
        "Terlambat",
        "Tidak Hadir",
        "Total Sesi",
        "Persentase (%)",
        "Status",
    ]
    start_row = 4
    for col_idx, text in enumerate(headers, start=1):
        cell = ws1.cell(row=start_row, column=col_idx, value=text)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = thin_border

    for idx, student in enumerate(report.students, start=1):
        row_num = start_row + idx
        status_text = "WARNING (<75%)" if student.warning else "AMAN"
        values = [
            idx,
            student.nim,
            student.student_name,
            student.hadir,
            student.terlambat,
            student.absent,
            student.total_sessions,
            student.attendance_percentage,
            status_text,
        ]
        for col_idx, val in enumerate(values, start=1):
            cell = ws1.cell(row=row_num, column=col_idx, value=val)
            cell.border = thin_border
            if col_idx in {1, 2, 4, 5, 6, 7, 8, 9}:
                cell.alignment = Alignment(horizontal="center")
            if col_idx == 8:
                cell.number_format = "0.00"
            if col_idx == 9:
                cell.fill = warn_fill if student.warning else ok_fill
                cell.font = warn_font if student.warning else ok_font

    _auto_fit_columns(ws1)

    # --- Sheet 2: Mahasiswa Warning (<75%) ---
    ws2 = wb.create_sheet(title="Warning (<75%)")
    ws2["A1"] = f"DAFTAR MAHASISWA BERISIKO (<75%) - {report.course_code}"
    ws2["A1"].font = title_font
    warn_headers = ["No", "NIM", "Nama Mahasiswa", "Hadir", "Terlambat", "Tidak Hadir", "Persentase (%)"]
    for col_idx, text in enumerate(warn_headers, start=1):
        cell = ws2.cell(row=3, column=col_idx, value=text)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")
        cell.border = thin_border

    if report.warning_students:
        for idx, student in enumerate(report.warning_students, start=1):
            row_num = 3 + idx
            row_vals = [
                idx,
                student.nim,
                student.student_name,
                student.hadir,
                student.terlambat,
                student.absent,
                student.attendance_percentage,
            ]
            for col_idx, val in enumerate(row_vals, start=1):
                cell = ws2.cell(row=row_num, column=col_idx, value=val)
                cell.border = thin_border
                cell.fill = warn_fill
                if col_idx == 7:
                    cell.number_format = "0.00"
                    cell.font = warn_font
    else:
        ws2["A4"] = "Tidak ada mahasiswa dengan presensi di bawah 75%."

    _auto_fit_columns(ws2)

    # --- Sheet 3: Riwayat Detail Sesi ---
    ws3 = wb.create_sheet(title="Detail Sesi")
    ws3["A1"] = f"LOG PRESENSI PER PERTEMUAN - {report.course_code}"
    ws3["A1"].font = title_font
    detail_headers = [
        "Pertemuan",
        "Tanggal",
        "Hari",
        "Jam Mulai",
        "NIM",
        "Nama Mahasiswa",
        "Status",
        "Waktu Scan (UTC)",
    ]
    for col_idx, text in enumerate(detail_headers, start=1):
        cell = ws3.cell(row=3, column=col_idx, value=text)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center")
        cell.border = thin_border

    sessions = (
        db.execute(
            select(AttendanceSession, Schedule)
            .join(Schedule, Schedule.id == AttendanceSession.schedule_id)
            .where(Schedule.course_id == course_id)
            .order_by(AttendanceSession.session_date, AttendanceSession.meeting_number)
        )
        .all()
    )
    enrolled_students = (
        db.execute(
            select(Student)
            .join(Enrollment, Enrollment.nim == Student.nim)
            .where(Enrollment.course_id == course_id)
            .order_by(Student.nim)
        )
        .scalars()
        .all()
    )

    session_ids = [s.id for s, _ in sessions]
    record_map: dict[tuple[int, str], AttendanceRecord] = {}
    if session_ids:
        recs = (
            db.execute(
                select(AttendanceRecord).where(AttendanceRecord.session_id.in_(session_ids))
            )
            .scalars()
            .all()
        )
        for rec in recs:
            record_map[(rec.session_id, rec.nim)] = rec

    row_cursor = 4
    for sess, sched in sessions:
        day_name = DAY_NAMES_ID.get(sched.day_of_week, str(sched.day_of_week))
        start_str = sched.start_time.strftime("%H:%M")
        for st in enrolled_students:
            rec = record_map.get((sess.id, st.nim))
            rec_status = rec.status.upper() if rec else "ABSENT"
            scan_ts = rec.scanned_at.strftime("%Y-%m-%d %H:%M:%S") if rec else "-"
            vals = [
                sess.meeting_number,
                sess.session_date.isoformat(),
                day_name,
                start_str,
                st.nim,
                st.name,
                rec_status,
                scan_ts,
            ]
            for col_idx, val in enumerate(vals, start=1):
                cell = ws3.cell(row=row_cursor, column=col_idx, value=val)
                cell.border = thin_border
                if col_idx == 7 and rec_status == "ABSENT":
                    cell.fill = warn_fill
                    cell.font = warn_font
            row_cursor += 1

    _auto_fit_columns(ws3)

    output = io.BytesIO()
    wb.save(output)
    filename = f"laporan_presensi_{report.course_code}.xlsx"
    return output.getvalue(), filename
