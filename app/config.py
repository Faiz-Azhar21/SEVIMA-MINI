"""Konfigurasi aplikasi Modul Presensi QR Code."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo


def _load_dotenv() -> None:
    """Memuat variabel dari file .env lokal jika tersedia."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


class Settings:
    """Pengaturan terpusat untuk sistem presensi QR code."""

    SECRET_KEY: str = os.getenv(
        "SECRET_KEY",
        "dev-presensi-qr-secret-key-minggu-12-ganti-di-production",
    )
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")

    # Durasi validasi QR & jendela waktu presensi
    QR_VALID_MINUTES: int = int(os.getenv("QR_VALID_MINUTES", "15"))
    HADIR_WINDOW_MINUTES: int = int(os.getenv("HADIR_WINDOW_MINUTES", "15"))
    TERLAMBAT_MAX_MINUTES: int = int(os.getenv("TERLAMBAT_MAX_MINUTES", "30"))
    ATTENDANCE_WARNING_THRESHOLD: float = float(
        os.getenv("ATTENDANCE_WARNING_THRESHOLD", "75.0")
    )

    # Timezone kampus (default WIB / Asia/Jakarta)
    APP_TIMEZONE: str = os.getenv("APP_TIMEZONE", "Asia/Jakarta")

    # Rate limiting untuk mencegah spam scan
    RATE_LIMIT_MAX_REQUESTS: int = int(os.getenv("RATE_LIMIT_MAX_REQUESTS", "5"))
    RATE_LIMIT_WINDOW_SECONDS: int = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))

    # Database SQLite default
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./attendance.db")

    # Opsional: API key LLM untuk pengayaan AI Attendance Insights
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.APP_TIMEZONE)

    def now_local(self) -> datetime:
        """Waktu saat ini dalam timezone lokal kampus."""
        return datetime.now(self.tz)

    def now_utc(self) -> datetime:
        """Waktu saat ini dalam UTC."""
        return datetime.now(timezone.utc)


settings = Settings()

DAY_NAMES_ID: dict[int, str] = {
    0: "Senin",
    1: "Selasa",
    2: "Rabu",
    3: "Kamis",
    4: "Jumat",
    5: "Sabtu",
    6: "Minggu",
}
