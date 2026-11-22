"""Data awal (seed) realistis untuk demonstrasi Modul Presensi QR Code.

Menyiapkan:
- 3 Mata Kuliah (IF201 Algoritma, IF202 Basis Data, IF203 Pemrograman Web)
- 10 Mahasiswa dengan variasi enrollment (agar bisa menguji "tidak bisa scan kelas orang lain")
- Jadwal mingguan + 1 jadwal Live Demo aktif sesuai waktu lokal saat aplikasi berjalan
- Riwayat 6 pertemuan historis dengan pola kehadiran realistis:
  * Kelas IF201 Senin jam 07:00 memiliki tingkat absen tinggi (~40%+)
  * 5 mahasiswa berisiko (<75%) agar Report Warning & AI Early Warning langsung terlihat nyata
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    AttendanceRecord,
    AttendanceSession,
    Course,
    Enrollment,
    Schedule,
    Student,
)


def _past_weekdays(target_weekday: int, count: int, reference_date: date) -> list[date]:
    """Menghasilkan `count` tanggal masa lalu yang jatuh pada `target_weekday`."""
    days_back = (reference_date.weekday() - target_weekday) % 7
    if days_back == 0:
        days_back = 7
    latest = reference_date - timedelta(days=days_back)
    return [latest - timedelta(weeks=i) for i in reversed(range(count))]


def seed_database(db: Session) -> bool:
    """Mengisi data awal jika tabel mata kuliah masih kosong. Mengembalikan True bila men-seed."""
    existing_courses = db.execute(select(func.count(Course.id))).scalar_one() or 0
    if existing_courses > 0:
        return False

    # 1. Mata Kuliah
    c_algo = Course(code="IF201", name="Algoritma & Struktur Data", credits=3)
    c_db = Course(code="IF202", name="Basis Data Lanjut", credits=3)
    c_web = Course(code="IF203", name="Pemrograman Web", credits=3)
    db.add_all([c_algo, c_db, c_web])
    db.flush()

    # 2. Mahasiswa (10 mahasiswa)
    students_data = [
        ("2301001", "Alya Putri Rahmawati", "alya@kampus.ac.id"),
        ("2301002", "Bagas Pratama", "bagas@kampus.ac.id"),
        ("2301003", "Citra Dewi Lestari", "citra@kampus.ac.id"),
        ("2301004", "Dimas Saputra", "dimas@kampus.ac.id"),
        ("2301005", "Eka Wulandari", "eka@kampus.ac.id"),
        ("2301006", "Fajar Nugroho", "fajar@kampus.ac.id"),
        ("2301007", "Gita Permata Sari", "gita@kampus.ac.id"),
        ("2301008", "Hendra Wijaya", "hendra@kampus.ac.id"),
        ("2301009", "Intan Kusuma", "intan@kampus.ac.id"),
        ("2301010", "Joko Susanto", "joko@kampus.ac.id"),
    ]
    students = [Student(nim=n, name=nm, email=em) for n, nm, em in students_data]
    db.add_all(students)
    db.flush()

    # 3. Enrollment (KRS)
    # IF201: 2301001..2301008 (8 mhs)
    # IF202: 2301001..2301006, 2301009, 2301010 (8 mhs)
    # IF203: 2301001..2301007 (7 mhs — NIM 2301008..2301010 BUKAN peserta IF203)
    enrollment_map = {
        c_algo.id: [f"230100{i}" for i in range(1, 9)],
        c_db.id: [f"230100{i}" for i in range(1, 7)] + ["2301009", "2301010"],
        c_web.id: [f"230100{i}" for i in range(1, 8)],
    }
    for course_id, nims in enrollment_map.items():
        for nim in nims:
            db.add(Enrollment(nim=nim, course_id=course_id))
    db.flush()

    # 4. Jadwal Kuliah
    local_now = settings.now_local()
    demo_start = local_now.replace(second=0, microsecond=0)
    demo_end_dt = demo_start + timedelta(hours=2)
    demo_end_time = time(23, 59) if demo_end_dt.date() != demo_start.date() else demo_end_dt.time()

    sched_algo = Schedule(
        course_id=c_algo.id,
        lecturer_id="DSN001",
        lecturer_name="Dr. Andi Pratama, M.Kom.",
        day_of_week=0,  # Senin
        start_time=time(7, 0),
        end_time=time(9, 30),
        room="Ruang 301",
        latitude=-6.200000,
        longitude=106.816666,
        radius_meters=100.0,
        require_geolocation=False,
    )
    sched_db = Schedule(
        course_id=c_db.id,
        lecturer_id="DSN002",
        lecturer_name="Prof. Siti Aminah, Ph.D.",
        day_of_week=2,  # Rabu
        start_time=time(10, 0),
        end_time=time(12, 30),
        room="Ruang 204",
        latitude=-6.200200,
        longitude=106.816800,
        radius_meters=100.0,
        require_geolocation=False,
    )
    sched_web_live = Schedule(
        course_id=c_web.id,
        lecturer_id="DSN003",
        lecturer_name="Ir. Budi Santoso, M.T.",
        day_of_week=local_now.weekday(),
        start_time=demo_start.time(),
        end_time=demo_end_time,
        room="Lab Komputer 2 (Live Demo)",
        latitude=-6.200000,
        longitude=106.816666,
        radius_meters=150.0,
        require_geolocation=False,
    )
    db.add_all([sched_algo, sched_db, sched_web_live])
    db.flush()

    # 5. Riwayat 6 Pertemuan IF201 (Senin 07:00) — dirancang agar pola absen Senin pagi jelas
    # Pola kehadiran 6 pertemuan per NIM (H=hadir, T=terlambat, A=absent):
    algo_matrix: dict[str, list[str]] = {
        "2301001": ["H", "H", "H", "H", "H", "H"],  # 100%
        "2301002": ["H", "T", "H", "H", "T", "H"],  # 100% (sering terlambat)
        "2301003": ["A", "A", "H", "A", "A", "A"],  # 16.7% -> CRITICAL & sering absent Senin pagi
        "2301004": ["A", "A", "A", "T", "A", "H"],  # 33.3% -> CRITICAL & sering absent Senin pagi
        "2301005": ["A", "H", "A", "H", "A", "A"],  # 33.3% -> CRITICAL & sering absent Senin pagi
        "2301006": ["H", "H", "A", "A", "H", "T"],  # 66.7% -> WARNING (<75%)
        "2301007": ["H", "H", "H", "A", "H", "H"],  # 83.3%
        "2301008": ["A", "A", "H", "A", "T", "A"],  # 33.3% -> CRITICAL & sering absent Senin pagi
    }
    # Total absent IF201 Senin 07:00 = 20 / 48 = 41.67% (memicu rekomendasi reschedule!)
    # Total mahasiswa < 75% di IF201 = 5 mahasiswa (2301003, 2301004, 2301005, 2301006, 2301008)

    monday_dates = _past_weekdays(target_weekday=0, count=6, reference_date=local_now.date())
    for meeting_idx, sess_date in enumerate(monday_dates, start=1):
        opened_local = datetime.combine(sess_date, time(7, 0), tzinfo=settings.tz)
        opened_utc = opened_local.astimezone(timezone.utc)
        jti = uuid.uuid4().hex
        sess = AttendanceSession(
            schedule_id=sched_algo.id,
            session_date=sess_date,
            meeting_number=meeting_idx,
            active_jti=jti,
            opened_at=opened_utc,
            expires_at=opened_utc + timedelta(minutes=15),
            is_active=False,
        )
        db.add(sess)
        db.flush()

        for nim, statuses in algo_matrix.items():
            code = statuses[meeting_idx - 1]
            if code == "A":
                continue
            status_val = "hadir" if code == "H" else "terlambat"
            offset_min = 5 if code == "H" else 20
            db.add(
                AttendanceRecord(
                    session_id=sess.id,
                    schedule_id=sched_algo.id,
                    course_id=c_algo.id,
                    nim=nim,
                    status=status_val,
                    scanned_at=opened_utc + timedelta(minutes=offset_min),
                    token_jti=jti,
                )
            )

    # 6. Riwayat 4 Pertemuan IF202 (Rabu 10:00) — kelas sehat (~87.5% kehadiran)
    db_matrix: dict[str, list[str]] = {
        "2301001": ["H", "H", "H", "H"],
        "2301002": ["H", "H", "T", "H"],
        "2301003": ["H", "H", "H", "H"],  # Bagus di Rabu siang, tapi sering absen Senin pagi!
        "2301004": ["H", "H", "H", "A"],
        "2301005": ["H", "T", "H", "H"],
        "2301006": ["H", "H", "H", "H"],
        "2301009": ["H", "H", "H", "T"],
        "2301010": ["H", "A", "A", "H"],  # 50% di IF202
    }
    wednesday_dates = _past_weekdays(target_weekday=2, count=4, reference_date=local_now.date())
    for meeting_idx, sess_date in enumerate(wednesday_dates, start=1):
        opened_local = datetime.combine(sess_date, time(10, 0), tzinfo=settings.tz)
        opened_utc = opened_local.astimezone(timezone.utc)
        jti = uuid.uuid4().hex
        sess = AttendanceSession(
            schedule_id=sched_db.id,
            session_date=sess_date,
            meeting_number=meeting_idx,
            active_jti=jti,
            opened_at=opened_utc,
            expires_at=opened_utc + timedelta(minutes=15),
            is_active=False,
        )
        db.add(sess)
        db.flush()

        for nim, statuses in db_matrix.items():
            code = statuses[meeting_idx - 1]
            if code == "A":
                continue
            status_val = "hadir" if code == "H" else "terlambat"
            offset_min = 4 if code == "H" else 18
            db.add(
                AttendanceRecord(
                    session_id=sess.id,
                    schedule_id=sched_db.id,
                    course_id=c_db.id,
                    nim=nim,
                    status=status_val,
                    scanned_at=opened_utc + timedelta(minutes=offset_min),
                    token_jti=jti,
                )
            )

    db.commit()
    return True
