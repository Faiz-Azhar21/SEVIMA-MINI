"""Test Scheduled Jobs (APScheduler) untuk Generate Billing Semesteran & Reminder Harian."""

from __future__ import annotations

from datetime import date

from app.services.scheduler_service import BillingSchedulerManager, resolve_semester_for_date


def test_resolve_semester_for_date() -> None:
    sem_ganjil, start_ganjil = resolve_semester_for_date(date(2026, 9, 1))
    assert sem_ganjil == "2026/2027-Ganjil"
    assert start_ganjil == date(2026, 9, 1)

    sem_genap, start_genap = resolve_semester_for_date(date(2027, 2, 1))
    assert sem_genap == "2026/2027-Genap"
    assert start_genap == date(2027, 2, 1)


def test_apscheduler_registers_and_starts_cron_jobs() -> None:
    mgr = BillingSchedulerManager()
    mgr.start()
    try:
        jobs = mgr.get_jobs_info()
        job_ids = {j["id"] for j in jobs}
        assert "semester_billing_generator" in job_ids
        assert "daily_overdue_and_reminder" in job_ids
        for job in jobs:
            assert job["running"] is True
            assert job["next_run_time"] is not None
    finally:
        mgr.shutdown()
