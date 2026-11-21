"""Calendar Integration Basics — Ekspor iCalendar (.ics) sesuai RFC 5545 (Slide 16).

Aturan teknis RFC 5545 yang dipenuhi:
- Pemisah baris wajib ``CRLF`` (``\\r\\n``).
- Satu ``VEVENT`` mewakili satu semester kuliah memakai ``RRULE:FREQ=WEEKLY;UNTIL=...``.
- ``DTSTART``/``DTEND`` menggunakan ``TZID=Asia/Jakarta``, sehingga ``UNTIL`` wajib
  ditulis dalam UTC (akhiran ``Z``).
- ``UID`` stabil (``jadwal-{id}@sevima-mini``) dan ``SEQUENCE`` naik saat jadwal berubah,
  sehingga impor ulang memperbarui event lama bukan menduplikasi.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.scheduling.models import Jadwal

WIB = ZoneInfo("Asia/Jakarta")


def _escape_ics(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def buat_vevent(
    j: Jadwal,
    judul: str,
    awal: date,
    akhir: date,
    sequence: int | None = None,
) -> str:
    """Membuat satu blok VEVENT RFC 5545 untuk satu jadwal kuliah selama 1 semester."""
    seq = j.sequence if sequence is None else sequence
    # awal.weekday(): 0=Senin .. 6=Minggu; j.hari: 1=Senin .. 6=Sabtu
    pertama = awal + timedelta(days=(j.hari - 1 - awal.weekday()) % 7)
    dt_start = datetime.combine(pertama, j.jam_mulai)
    dt_end = datetime.combine(pertama, j.jam_selesai)

    # Jika DTSTART memakai TZID, nilai UNTIL di RRULE wajib dalam UTC (berakhiran Z)
    akhir_wib = datetime.combine(akhir, time(23, 59, 59), tzinfo=WIB)
    akhir_utc = akhir_wib.astimezone(timezone.utc)
    dtstamp = datetime.now(timezone.utc)

    lines = [
        "BEGIN:VEVENT",
        f"UID:jadwal-{j.id}@sevima-mini",
        f"SEQUENCE:{seq}",
        f"DTSTAMP:{dtstamp:%Y%m%dT%H%M%SZ}",
        f"DTSTART;TZID=Asia/Jakarta:{dt_start:%Y%m%dT%H%M%S}",
        f"DTEND;TZID=Asia/Jakarta:{dt_end:%Y%m%dT%H%M%S}",
        f"RRULE:FREQ=WEEKLY;UNTIL={akhir_utc:%Y%m%dT%H%M%SZ}",
        f"SUMMARY:{_escape_ics(judul)}",
        f"LOCATION:{_escape_ics(j.ruangan_kode)}",
        "END:VEVENT",
    ]
    return "\r\n".join(lines)


def export_jadwal_ics(
    items: list[tuple[Jadwal, str]],
    awal: date = date(2026, 9, 7),
    akhir: date = date(2026, 12, 18),
) -> str:
    """Membungkus seluruh jadwal mahasiswa dalam dokumen VCALENDAR RFC 5545 (CRLF)."""
    parts = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//SEVIMA-Mini//Jadwal//ID",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    for jadwal, judul in items:
        parts.append(buat_vevent(jadwal, judul, awal=awal, akhir=akhir))
    parts.append("END:VCALENDAR")
    return "\r\n".join(parts) + "\r\n"
