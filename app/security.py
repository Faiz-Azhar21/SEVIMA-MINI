"""Modul keamanan: JWT signing/verification, anti-replay, rate limiting, geolocation, dan RBAC."""

from __future__ import annotations

import math
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt
from fastapi import Header, HTTPException, status

from app.config import settings


class TokenValidationError(Exception):
    """Error khusus saat validasi token JWT presensi gagal."""

    def __init__(self, message: str, code: str = "INVALID_TOKEN") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


def create_qr_jwt(
    schedule_id: int,
    session_id: int,
    jti: str,
    valid_minutes: int | None = None,
    now_utc: datetime | None = None,
) -> tuple[str, datetime, datetime]:
    """Membuat token JWT HS256 dengan masa berlaku terbatas dan JTI unik."""
    duration = valid_minutes if valid_minutes is not None else settings.QR_VALID_MINUTES
    issued_at = now_utc or datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(minutes=duration)

    payload: dict[str, Any] = {
        "schedule_id": schedule_id,
        "session_id": session_id,
        "jti": jti,
        "type": "attendance_qr",
        "iat": issued_at,
        "exp": expires_at,
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, issued_at, expires_at


def decode_qr_jwt(token: str, now_utc: datetime | None = None) -> dict[str, Any]:
    """Memvalidasi tanda tangan dan masa berlaku (exp) token JWT QR."""
    options: dict[str, Any] = {"require": ["schedule_id", "iat", "exp"]}
    if now_utc is not None:
        options["verify_exp"] = False
        options["verify_iat"] = False

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options=options,
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenValidationError(
            "QR code sudah kadaluarsa (expired). Silakan minta dosen men-generate QR baru.",
            code="QR_EXPIRED",
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise TokenValidationError(
            "QR code tidak valid atau telah dimodifikasi.",
            code="QR_INVALID",
        ) from exc

    if now_utc is not None:
        check_ts = now_utc.timestamp()
        exp_ts = float(payload["exp"])
        iat_ts = float(payload["iat"])
        if check_ts > exp_ts:
            raise TokenValidationError(
                "QR code sudah kadaluarsa (expired). Silakan minta dosen men-generate QR baru.",
                code="QR_EXPIRED",
            )
        if iat_ts > check_ts:
            raise TokenValidationError(
                "QR code belum berlaku (iat berada di masa depan).",
                code="QR_INVALID",
            )

    return payload


def haversine_distance_meters(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """Menghitung jarak (meter) antara dua koordinat GPS menggunakan rumus Haversine."""
    earth_radius_m = 6_371_000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return round(earth_radius_m * c, 2)


class SlidingWindowRateLimiter:
    """Rate limiter berbasis sliding window di memori untuk mencegah spam scan."""

    def __init__(
        self,
        max_requests: int | None = None,
        window_seconds: int | None = None,
    ) -> None:
        self.max_requests = (
            max_requests if max_requests is not None else settings.RATE_LIMIT_MAX_REQUESTS
        )
        self.window_seconds = (
            window_seconds if window_seconds is not None else settings.RATE_LIMIT_WINDOW_SECONDS
        )
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, now_ts: float | None = None) -> tuple[bool, int]:
        """Memeriksa apakah key masih dalam batas kuota request.

        Returns:
            (allowed, retry_after_seconds)
        """
        current = now_ts if now_ts is not None else time.monotonic()
        cutoff = current - self.window_seconds

        with self._lock:
            bucket = self._hits[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            if len(bucket) >= self.max_requests:
                retry_after = max(1, math.ceil(self.window_seconds - (current - bucket[0])))
                return False, retry_after

            bucket.append(current)
            return True, 0

    def reset(self) -> None:
        """Mengosongkan histori rate limit (berguna untuk pengujian)."""
        with self._lock:
            self._hits.clear()


scan_rate_limiter = SlidingWindowRateLimiter()


def require_lecturer_role(
    x_role: Optional[str] = Header(default=None, alias="X-Role"),
) -> str:
    """Guard sederhana untuk mencegah mahasiswa men-generate QR atau mengekspor laporan dosen.

    Jika header X-Role tidak dikirim, default 'dosen' agar endpoint tetap dapat diakses langsung
    sesuai spesifikasi Step 1 (GET /attendance/qr/{schedule_id}). Jika X-Role dikirim sebagai
    'mahasiswa' atau role non-dosen lainnya, akses ditolak (403).
    """
    if x_role is None or not x_role.strip():
        return "dosen"

    normalized = x_role.strip().lower()
    if normalized not in {"dosen", "lecturer", "admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Akses ditolak: hanya dosen yang diizinkan melakukan aksi ini.",
        )
    return normalized
