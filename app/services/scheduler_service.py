"""Scheduled Jobs menggunakan APScheduler.

Job otomatis:
1. `semester_billing_generator`:
   Jalan otomatis setiap awal semester (1 Februari untuk Genap, 1 September untuk Ganjil)
   untuk membuat tagihan SPP seluruh mahasiswa aktif.
2. `daily_overdue_and_reminder`:
   Jalan otomatis setiap hari pukul 08:00 WIB untuk menandai tagihan overdue,
   menghitung denda keterlambatan, dan mengirim email reminder otomatis.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app import database
from app.config import TIMEZONE
from app.services.billing_service import apply_overdue_and_penalties, generate_billing

logger = logging.getLogger(__name__)


def resolve_semester_for_date(ref_date: date | None = None) -> tuple[str, date]:
    """Menentukan kode semester & tanggal mulai semester berdasarkan tanggal saat ini."""
    today = ref_date or date.today()
    if 2 <= today.month <= 7:
        # Semester Genap: mulai 1 Februari
        semester = f"{today.year - 1}/{today.year}-Genap"
        start = date(today.year, 2, 1)
    elif today.month >= 8:
        # Semester Ganjil: mulai 1 September
        semester = f"{today.year}/{today.year + 1}-Ganjil"
        start = date(today.year, 9, 1)
    else:
        # Januari masih termasuk tahun akademik sebelumnya (persiapan Genap)
        semester = f"{today.year - 1}/{today.year}-Genap"
        start = date(today.year, 2, 1)
    return semester, start


def job_generate_semester_billing() -> dict[str, Any]:
    """Eksekusi cron job pembuatan billing otomatis awal semester."""
    semester, sem_start = resolve_semester_for_date()
    db = database.SessionLocal()
    try:
        result = generate_billing(db, semester=semester, semester_start=sem_start)
        logger.info("[APScheduler] Generate billing semester %s: %s", semester, result)
        return result
    finally:
        db.close()


def job_daily_overdue_and_reminders() -> dict[str, Any]:
    """Eksekusi cron job harian: cek overdue, hitung denda, dan kirim reminder otomatis."""
    db = database.SessionLocal()
    try:
        result = apply_overdue_and_penalties(db, as_of_date=date.today(), send_reminders=True)
        logger.info("[APScheduler] Daily overdue & reminder job: %s", result)
        return result
    finally:
        db.close()


class BillingSchedulerManager:
    """Wrapper pengelolaan siklus hidup APScheduler."""

    def __init__(self) -> None:
        self.scheduler = BackgroundScheduler(timezone=TIMEZONE)
        self._configured = False

    def configure_jobs(self) -> None:
        if self._configured:
            return

        # Cron job otomatis tiap awal semester: 1 Feb & 1 Sep pukul 00:05
        self.scheduler.add_job(
            job_generate_semester_billing,
            trigger=CronTrigger(month="2,9", day="1", hour="0", minute="5", timezone=TIMEZONE),
            id="semester_billing_generator",
            name="Generate Tagihan SPP Awal Semester",
            replace_existing=True,
        )

        # Cron job harian: pukul 08:00 untuk update status overdue, denda, dan reminder otomatis
        self.scheduler.add_job(
            job_daily_overdue_and_reminders,
            trigger=CronTrigger(hour="8", minute="0", timezone=TIMEZONE),
            id="daily_overdue_and_reminder",
            name="Cek Overdue, Hitung Denda & Kirim Reminder Harian",
            replace_existing=True,
        )
        self._configured = True

    def start(self) -> None:
        self.configure_jobs()
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("[APScheduler] Scheduler aktif dengan %d job.", len(self.scheduler.get_jobs()))

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def get_jobs_info(self) -> list[dict[str, Any]]:
        self.configure_jobs()
        jobs_info: list[dict[str, Any]] = []
        for job in self.scheduler.get_jobs():
            next_run = getattr(job, "next_run_time", None)
            jobs_info.append(
                {
                    "id": job.id,
                    "name": job.name,
                    "trigger": str(job.trigger),
                    "next_run_time": next_run.isoformat() if next_run else None,
                    "running": self.scheduler.running,
                }
            )
        return jobs_info


scheduler_manager = BillingSchedulerManager()
