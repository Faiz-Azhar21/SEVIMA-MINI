"""Service 4: AI Attendance Insights & Pattern Detection (15%).

Menganalisis data presensi (baik dari database maupun input JSON array langsung):
1. Menghitung persentase kehadiran per mahasiswa
2. Mengidentifikasi mahasiswa dengan presensi <75% (early warning)
3. Mendeteksi pola hari/jam dengan tingkat ketidakhadiran (absent rate) tinggi
4. Menghasilkan rekomendasi tindakan (actions) + insights dalam format JSON terstruktur
5. Opsional: memperkaya narasi insight melalui LLM API (Gemini / OpenAI) jika API key tersedia
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import httpx
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
    AIActionItem,
    AIInsightItem,
    AIInsightsResponse,
    RawAttendanceRecordInput,
    StudentRiskSummary,
    TimeSlotPattern,
)


def _normalize_status(raw_status: str) -> str:
    s = raw_status.strip().lower()
    if s in {"hadir", "present"}:
        return "hadir"
    if s in {"terlambat", "late"}:
        return "terlambat"
    return "absent"


def _time_period_label(time_str: str | None) -> str:
    if not time_str:
        return ""
    try:
        hour = int(time_str.split(":")[0])
    except (ValueError, IndexError):
        return ""
    if hour < 11:
        return "pagi"
    if hour < 15:
        return "siang"
    if hour < 18:
        return "sore"
    return "malam"


def _classify_risk(percentage: float) -> str:
    if percentage < 50.0:
        return "CRITICAL"
    if percentage < 65.0:
        return "HIGH"
    return "WARNING"


def build_attendance_dataset_from_db(
    db: Session, course_id: int | None = None
) -> list[RawAttendanceRecordInput]:
    """Mengonversi sesi kuliah, enrollment, dan log scan DB menjadi array attendance_records.

    Mahasiswa yang terdaftar pada suatu MK tetapi tidak melakukan scan pada sesi tertentu
    otomatis dipetakan sebagai status 'absent' sehingga deteksi pola dan persentase akurat.
    """
    query = (
        select(AttendanceSession, Schedule, Course)
        .join(Schedule, Schedule.id == AttendanceSession.schedule_id)
        .join(Course, Course.id == Schedule.course_id)
        .order_by(AttendanceSession.session_date, Schedule.start_time)
    )
    if course_id is not None:
        query = query.where(Course.id == course_id)

    session_rows = db.execute(query).all()
    if not session_rows:
        return []

    course_ids = {course.id for _, _, course in session_rows}
    session_ids = [session.id for session, _, _ in session_rows]

    enrollment_rows = db.execute(
        select(Enrollment.course_id, Student)
        .join(Student, Student.nim == Enrollment.nim)
        .where(Enrollment.course_id.in_(course_ids))
    ).all()

    students_by_course: dict[int, list[Student]] = defaultdict(list)
    for c_id, student in enrollment_rows:
        students_by_course[c_id].append(student)

    records = (
        db.execute(
            select(AttendanceRecord).where(AttendanceRecord.session_id.in_(session_ids))
        )
        .scalars()
        .all()
    )
    record_map: dict[tuple[int, str], AttendanceRecord] = {
        (rec.session_id, rec.nim): rec for rec in records
    }

    dataset: list[RawAttendanceRecordInput] = []
    for sess, sched, course in session_rows:
        day_name = DAY_NAMES_ID.get(sched.day_of_week, str(sched.day_of_week))
        time_str = sched.start_time.strftime("%H:%M")
        date_str = sess.session_date.isoformat()

        for student in students_by_course.get(course.id, []):
            rec = record_map.get((sess.id, student.nim))
            rec_status = rec.status if rec else "absent"
            dataset.append(
                RawAttendanceRecordInput(
                    nim=student.nim,
                    student_name=student.name,
                    course_code=course.code,
                    course_name=course.name,
                    day=day_name,
                    time=time_str,
                    date=date_str,
                    status=rec_status,  # type: ignore[arg-type]
                )
            )

    return dataset


def _try_llm_enrichment(summary_payload: dict[str, Any]) -> dict[str, Any] | None:
    """Opsional: mengirim ringkasan statistik terverifikasi ke LLM untuk pengayaan rekomendasi."""
    prompt = (
        "Anda adalah AI Attendance Analyzer kampus. Berdasarkan data statistik presensi "
        "terverifikasi berikut, berikan JSON valid dengan kunci 'insights' (array objek "
        "{category, severity, summary}) dan 'actions' (array objek "
        "{priority, target_type, target, recommendation, reason}) dalam Bahasa Indonesia.\n"
        f"Data: {json.dumps(summary_payload, ensure_ascii=False)}"
    )

    if settings.GEMINI_API_KEY:
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.0-flash:generateContent?key={settings.GEMINI_API_KEY}"
        )
        try:
            resp = httpx.post(
                url,
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"responseMimeType": "application/json"},
                },
                timeout=12.0,
            )
            resp.raise_for_status()
            text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(text)
            if isinstance(parsed, dict) and "insights" in parsed and "actions" in parsed:
                return parsed
        except Exception:
            return None

    if settings.OPENAI_API_KEY:
        try:
            resp = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                json={
                    "model": "gpt-4o-mini",
                    "response_format": {"type": "json_object"},
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=12.0,
            )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"]
            parsed = json.loads(text)
            if isinstance(parsed, dict) and "insights" in parsed and "actions" in parsed:
                return parsed
        except Exception:
            return None

    return None


def analyze_attendance_records(
    records: list[RawAttendanceRecordInput],
    use_llm_if_configured: bool = True,
) -> AIInsightsResponse:
    """Mesin utama AI Attendance Analyzer sesuai Step 3 tugas."""
    now_utc = datetime.now(timezone.utc)
    if not records:
        return AIInsightsResponse(
            analysis_mode="statistical_ai_engine",
            generated_at=now_utc,
            early_warning_headline="Belum ada data presensi yang dapat dianalisis.",
            summary={
                "total_records": 0,
                "total_students": 0,
                "at_risk_students_count": 0,
                "overall_attendance_percentage": 0.0,
            },
            student_percentages=[],
            at_risk_students=[],
            high_absence_patterns=[],
            insights=[],
            actions=[],
        )

    # Agregasi per mahasiswa (overall) & per (mahasiswa, hari) & per (kelas, hari, jam)
    student_stats: dict[str, dict[str, Any]] = {}
    student_day_stats: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {"total": 0, "absent": 0, "times": set()}
    )
    slot_stats: dict[tuple[str, str, str, str], dict[str, int]] = defaultdict(
        lambda: {"total": 0, "absent": 0, "terlambat": 0}
    )

    total_attended = 0
    total_absent = 0
    total_terlambat = 0

    for rec in records:
        norm = _normalize_status(rec.status)
        name = rec.student_name or f"Mahasiswa {rec.nim}"
        course_code = rec.course_code or "UMUM"
        course_name = rec.course_name or course_code
        day_label = rec.day or "Tidak diketahui"
        time_label = rec.time or "Tidak diketahui"

        if rec.nim not in student_stats:
            student_stats[rec.nim] = {
                "nim": rec.nim,
                "student_name": name,
                "courses": set(),
                "total": 0,
                "hadir": 0,
                "terlambat": 0,
                "absent": 0,
            }

        st = student_stats[rec.nim]
        st["courses"].add(course_code)
        st["total"] += 1

        if norm == "hadir":
            st["hadir"] += 1
            total_attended += 1
        elif norm == "terlambat":
            st["terlambat"] += 1
            total_attended += 1
            total_terlambat += 1
        else:
            st["absent"] += 1
            total_absent += 1

        if rec.day:
            sd = student_day_stats[(rec.nim, day_label)]
            sd["total"] += 1
            if norm == "absent":
                sd["absent"] += 1
            if rec.time:
                sd["times"].add(rec.time)

        if rec.day or rec.time:
            slot = slot_stats[(course_code, course_name, day_label, time_label)]
            slot["total"] += 1
            if norm == "absent":
                slot["absent"] += 1
            elif norm == "terlambat":
                slot["terlambat"] += 1

    # 1 & 2. Persentase kehadiran per mahasiswa & identifikasi <75% (warning)
    student_percentages: list[dict[str, Any]] = []
    at_risk_students: list[StudentRiskSummary] = []

    for nim, st in sorted(student_stats.items()):
        attended = st["hadir"] + st["terlambat"]
        pct = round((attended / st["total"]) * 100.0, 2) if st["total"] > 0 else 100.0
        warning = pct < settings.ATTENDANCE_WARNING_THRESHOLD
        courses_list = sorted(st["courses"])

        student_percentages.append(
            {
                "nim": nim,
                "student_name": st["student_name"],
                "courses": courses_list,
                "total_sessions": st["total"],
                "hadir": st["hadir"],
                "terlambat": st["terlambat"],
                "absent": st["absent"],
                "attendance_percentage": pct,
                "warning": warning,
            }
        )

        if warning:
            at_risk_students.append(
                StudentRiskSummary(
                    nim=nim,
                    student_name=st["student_name"],
                    course_code=", ".join(courses_list),
                    total_sessions=st["total"],
                    attended=attended,
                    absent=st["absent"],
                    terlambat=st["terlambat"],
                    attendance_percentage=pct,
                    risk_level=_classify_risk(pct),  # type: ignore[arg-type]
                )
            )

    at_risk_students.sort(key=lambda item: item.attendance_percentage)

    # 3. Deteksi pattern hari/jam dengan absen rate tinggi (>= 30% dan minimal 3 record)
    high_absence_patterns: list[TimeSlotPattern] = []
    for (c_code, c_name, day_label, time_label), metrics in slot_stats.items():
        if metrics["total"] < 3:
            continue
        absent_rate = round((metrics["absent"] / metrics["total"]) * 100.0, 2)
        if absent_rate >= 30.0:
            high_absence_patterns.append(
                TimeSlotPattern(
                    course_code=c_code,
                    course_name=c_name,
                    day=day_label,
                    time_slot=time_label,
                    total_records=metrics["total"],
                    absent_count=metrics["absent"],
                    absent_rate_percentage=absent_rate,
                )
            )

    high_absence_patterns.sort(key=lambda item: item.absent_rate_percentage, reverse=True)

    # 4. Generate structured insights & actions
    insights: list[AIInsightItem] = []
    actions: list[AIActionItem] = []

    if at_risk_students:
        early_warning_headline = (
            f"{len(at_risk_students)} mahasiswa berisiko tidak memenuhi syarat presensi "
            f"(<{settings.ATTENDANCE_WARNING_THRESHOLD:.0f}%)"
        )
        insights.append(
            AIInsightItem(
                category="early_warning",
                severity="high",
                summary=early_warning_headline,
                metrics={
                    "at_risk_count": len(at_risk_students),
                    "threshold": settings.ATTENDANCE_WARNING_THRESHOLD,
                    "critical_count": sum(
                        1 for s in at_risk_students if s.risk_level == "CRITICAL"
                    ),
                },
            )
        )
    else:
        early_warning_headline = (
            "Seluruh mahasiswa saat ini memenuhi ambang batas minimal presensi (>=75%)."
        )

    # Pola absen per mahasiswa per hari/waktu (mis. "Mahasiswa X sering absent hari Senin pagi")
    flagged_student_days: set[str] = set()
    for (nim, day_label), sd in sorted(student_day_stats.items()):
        if sd["total"] < 2 or sd["absent"] < 2:
            continue
        day_absent_rate = round((sd["absent"] / sd["total"]) * 100.0, 2)
        if day_absent_rate >= 50.0:
            st = student_stats[nim]
            sample_time = sorted(sd["times"])[0] if sd["times"] else None
            period = _time_period_label(sample_time)
            day_phrase = f"{day_label} {period}".strip()
            time_note = f" ({sample_time})" if sample_time else ""
            flagged_student_days.add(nim)

            insights.append(
                AIInsightItem(
                    category="student_pattern",
                    severity="high" if day_absent_rate >= 70.0 else "medium",
                    summary=(
                        f"Mahasiswa {st['student_name']} ({nim}) sering absent hari "
                        f"{day_phrase}{time_note} — tidak hadir {sd['absent']} dari "
                        f"{sd['total']} sesi ({day_absent_rate:.0f}%)."
                    ),
                    metrics={
                        "nim": nim,
                        "day": day_label,
                        "time": sample_time,
                        "absent_count": sd["absent"],
                        "total_sessions": sd["total"],
                        "absent_rate_percentage": day_absent_rate,
                    },
                )
            )
            actions.append(
                AIActionItem(
                    priority="high",
                    target_type="student",
                    target=f"{st['student_name']} ({nim})",
                    recommendation=(
                        f"Mahasiswa {st['student_name']} sering absent {day_phrase} "
                        "-> hubungi untuk konseling akademik"
                    ),
                    reason=(
                        f"Tingkat absen pada hari {day_phrase} mencapai {day_absent_rate:.0f}% "
                        f"({sd['absent']}/{sd['total']} sesi)."
                    ),
                )
            )

    # Rekomendasi untuk mahasiswa berisiko lainnya yang belum masuk pola hari spesifik
    for risk in at_risk_students:
        if risk.nim not in flagged_student_days:
            actions.append(
                AIActionItem(
                    priority="high" if risk.risk_level in {"CRITICAL", "HIGH"} else "medium",
                    target_type="student",
                    target=f"{risk.student_name} ({risk.nim})",
                    recommendation=(
                        f"Kirim peringatan dini (early warning) ke {risk.student_name} "
                        "dan jadwalkan pembinaan dosen wali"
                    ),
                    reason=(
                        f"Persentase kehadiran saat ini {risk.attendance_percentage:.1f}% "
                        f"(di bawah batas minimum 75%)."
                    ),
                )
            )

    # Pola kelas/jam dengan absen rate tinggi
    for pattern in high_absence_patterns:
        insights.append(
            AIInsightItem(
                category="schedule_pattern",
                severity="high" if pattern.absent_rate_percentage >= 40.0 else "medium",
                summary=(
                    f"Kelas {pattern.course_code} ({pattern.course_name}) pada hari "
                    f"{pattern.day} jam {pattern.time_slot} memiliki absen rate "
                    f"{pattern.absent_rate_percentage:.1f}% "
                    f"({pattern.absent_count}/{pattern.total_records} data)."
                ),
                metrics={
                    "course_code": pattern.course_code,
                    "day": pattern.day,
                    "time_slot": pattern.time_slot,
                    "absent_rate_percentage": pattern.absent_rate_percentage,
                },
            )
        )
        actions.append(
            AIActionItem(
                priority="high" if pattern.absent_rate_percentage >= 40.0 else "medium",
                target_type="course_schedule",
                target=f"{pattern.course_code} ({pattern.day} {pattern.time_slot})",
                recommendation=(
                    f"Kelas {pattern.course_code} di jam {pattern.time_slot} absen rate "
                    f"{pattern.absent_rate_percentage:.0f}% -> pertimbangkan reschedule "
                    "atau evaluasi metode perkuliahan"
                ),
                reason=(
                    f"Tingkat ketidakhadiran kelas pada slot {pattern.day} {pattern.time_slot} "
                    f"melebihi ambang 30%."
                ),
            )
        )

    # Tren keterlambatan tinggi per mahasiswa (>= 35% dari kehadiran)
    for nim, st in sorted(student_stats.items()):
        if st["total"] >= 3 and st["terlambat"] >= 2:
            late_rate = round((st["terlambat"] / st["total"]) * 100.0, 2)
            if late_rate >= 35.0:
                insights.append(
                    AIInsightItem(
                        category="lateness_trend",
                        severity="low",
                        summary=(
                            f"Mahasiswa {st['student_name']} ({nim}) sering datang terlambat "
                            f"({st['terlambat']} dari {st['total']} sesi / {late_rate:.0f}%)."
                        ),
                        metrics={
                            "nim": nim,
                            "terlambat": st["terlambat"],
                            "total_sessions": st["total"],
                            "late_rate_percentage": late_rate,
                        },
                    )
                )

    overall_pct = round((total_attended / len(records)) * 100.0, 2)
    summary_dict = {
        "total_records": len(records),
        "total_students": len(student_stats),
        "at_risk_students_count": len(at_risk_students),
        "overall_attendance_percentage": overall_pct,
        "overall_absent_percentage": round((total_absent / len(records)) * 100.0, 2),
        "total_terlambat": total_terlambat,
    }

    analysis_mode = "statistical_ai_engine"
    if use_llm_if_configured and (settings.GEMINI_API_KEY or settings.OPENAI_API_KEY):
        llm_data = _try_llm_enrichment(
            {
                "summary": summary_dict,
                "at_risk_students": [r.model_dump() for r in at_risk_students],
                "high_absence_patterns": [p.model_dump() for p in high_absence_patterns],
            }
        )
        if llm_data:
            analysis_mode = "llm_hybrid"
            # Tambahkan insight/action dari LLM bila valid secara skema
            for raw_ins in llm_data.get("insights", []):
                if isinstance(raw_ins, dict) and raw_ins.get("summary"):
                    cat = raw_ins.get("category", "early_warning")
                    if cat not in {
                        "early_warning",
                        "student_pattern",
                        "schedule_pattern",
                        "lateness_trend",
                    }:
                        cat = "early_warning"
                    sev = raw_ins.get("severity", "medium")
                    if sev not in {"high", "medium", "low"}:
                        sev = "medium"
                    insights.append(
                        AIInsightItem(
                            category=cat,  # type: ignore[arg-type]
                            severity=sev,  # type: ignore[arg-type]
                            summary=f"[AI] {raw_ins['summary']}",
                        )
                    )

    return AIInsightsResponse(
        analysis_mode=analysis_mode,  # type: ignore[arg-type]
        generated_at=now_utc,
        early_warning_headline=early_warning_headline,
        summary=summary_dict,
        student_percentages=student_percentages,
        at_risk_students=at_risk_students,
        high_absence_patterns=high_absence_patterns,
        insights=insights,
        actions=actions,
    )
