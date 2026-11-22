"""Konfigurasi aplikasi Modul Keuangan (SPP)."""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RECEIPTS_DIR = BASE_DIR / "receipts"

# Database
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{(BASE_DIR / 'spp_keuangan.db').as_posix()}")

# Webhook security secret (HMAC-SHA256)
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "spp-webhook-secret-2026")

# Tarif SPP per Program Studi (sesuai spesifikasi Step 1)
SPP_TARIFF_BY_PRODI: dict[str, int] = {
    "Teknik": 5_000_000,
    "Ekonomi": 4_000_000,
}
DEFAULT_SPP_TARIFF: int = 4_500_000

# Due date: 2 minggu (14 hari) setelah semester start
BILLING_DUE_DAYS: int = 14

# Aturan denda keterlambatan:
# 0.5% per hari keterlambatan dari base_amount, dengan cap maksimal 10% dari base_amount.
LATE_FEE_DAILY_RATE: float = float(os.getenv("LATE_FEE_DAILY_RATE", "0.005"))
LATE_FEE_MAX_RATE: float = float(os.getenv("LATE_FEE_MAX_RATE", "0.10"))

# Reminder otomatis dikirim mulai H-3 sebelum due date & berkala jika overdue
REMINDER_DAYS_BEFORE_DUE: int = 3

# Opsional: konfigurasi SMTP asli (jika kosong, otomatis pakai mode simulasi + simpan file HTML receipt)
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "keuangan@kampus.ac.id")

# Opsional: API key LLM untuk memperkaya narasi AI Financial Insights (jika kosong gunakan engine analitik lokal)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Scheduler toggle (bisa dimatikan saat unit test)
ENABLE_SCHEDULER = os.getenv("ENABLE_SCHEDULER", "true").lower() == "true"
TIMEZONE = os.getenv("APP_TIMEZONE", "Asia/Jakarta")
