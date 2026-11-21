"""Pengujian API Conflict Resolver, RBAC Admin, Prinsip Satu Pintu (409), & Ekspor .ics."""

from __future__ import annotations

import json

from app.main import app
from app.scheduling.router import get_llm

ADMIN_HEADERS = {"X-Role": "admin_akademik"}


class _StaticFakeLLM:
    def __init__(self, payload: list[dict]) -> None:
        self._text = json.dumps(payload)

    def complete(self, prompt: str) -> str:
        return self._text


def test_rbac_require_admin(client):
    """Endpoint admin wajib menolak akses tanpa header X-Role admin_akademik (HTTP 403)."""
    assert client.get("/api/jadwal/conflicts").status_code == 403
    assert client.get("/api/jadwal/conflicts", headers={"X-Role": "mahasiswa"}).status_code == 403
    assert client.get("/api/jadwal/conflicts", headers=ADMIN_HEADERS).status_code == 200


def test_dashboard_html_tersaji(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Conflict Resolver" in resp.text


def test_conflict_resolver_flow_dan_race_condition_409(client):
    """Menguji alur lengkap: lihat konflik -> saran AI -> terapkan satu pintu -> race condition 409."""
    # 1. Konflik awal: 1 room_conflict (#12, #15) dan 1 lecturer_conflict (#17, #21)
    r_conf = client.get("/api/jadwal/conflicts", headers=ADMIN_HEADERS)
    assert r_conf.status_code == 200
    conflicts = r_conf.json()
    types = {c["type"] for c in conflicts}
    assert types == {"room_conflict", "lecturer_conflict"}

    # 2. Saran AI dengan FakeLLM (DI override)
    app.dependency_overrides[get_llm] = lambda: _StaticFakeLLM(
        [
            {"hari": 3, "jam_mulai": "13:00", "ruangan": "B201", "reason": "pagi/siang aman"},
            {"hari": 2, "jam_mulai": "10:00", "ruangan": "Z999", "reason": "fiktif"},
        ]
    )
    r_sug = client.get("/api/jadwal/12/suggestions", headers=ADMIN_HEADERS)
    assert r_sug.status_code == 200
    saran = r_sug.json()
    assert len(saran) == 1
    assert saran[0]["ruangan"] == "B201"

    # 3. Terapkan saran via satu pintu POST /api/jadwal/12/apply
    r_apply = client.post("/api/jadwal/12/apply", json=saran[0], headers=ADMIN_HEADERS)
    assert r_apply.status_code == 200
    updated = r_apply.json()
    assert updated["hari"] == 3
    assert updated["ruangan_kode"] == "B201"
    assert updated["sequence"] == 1

    # Konflik ruangan (#12, #15) kini hilang
    remaining = client.get("/api/jadwal/conflicts", headers=ADMIN_HEADERS).json()
    assert all(c["type"] != "room_conflict" for c in remaining)

    # KRS Rina menjadi REVISION, log notifikasi & outbox terisi
    krs_list = client.get("/api/krs", headers=ADMIN_HEADERS).json()
    rina = next(k for k in krs_list if k["nim"] == "2301001")
    assert rina["status"] == "REVISION"

    logs = client.get("/api/logs/notifications", headers=ADMIN_HEADERS).json()
    assert {l["channel"] for l in logs} == {"EMAIL", "SMS", "PUSH"}

    # 4. Simulasi race condition: admin lain mencoba menerapkan Jadwal #15 ke slot yg baru diambil #12
    stale_saran = {"hari": 3, "jam_mulai": "13:00", "ruangan": "B201", "reason": "stale"}
    r_race = client.post("/api/jadwal/15/apply", json=stale_saran, headers=ADMIN_HEADERS)
    assert r_race.status_code == 409


def test_ekspor_icalendar_rfc5545_dan_sequence_naik(client):
    """Memverifikasi format .ics: text/calendar, CRLF, TZID+UNTIL UTC, UID stabil, SEQUENCE naik."""
    r1 = client.get("/api/mahasiswa/2301001/jadwal.ics")
    assert r1.status_code == 200
    assert r1.headers["content-type"].startswith("text/calendar")

    body1 = r1.text
    assert "BEGIN:VCALENDAR\r\n" in body1
    assert "END:VCALENDAR\r\n" in body1
    # Pastikan tidak ada LF telanjang tanpa CR
    assert "\n" not in body1.replace("\r\n", "")
    assert "UID:jadwal-12@sevima-mini\r\n" in body1
    assert "SEQUENCE:0\r\n" in body1
    assert "DTSTART;TZID=Asia/Jakarta:" in body1
    assert "RRULE:FREQ=WEEKLY;UNTIL=" in body1
    # UNTIL wajib berakhiran Z (UTC)
    until_lines = [ln for ln in body1.split("\r\n") if ln.startswith("RRULE:")]
    assert len(until_lines) >= 1
    assert all(ln.endswith("Z") for ln in until_lines)

    # Ubah Jadwal #12 -> SEQUENCE harus naik ke 1 dengan UID yang sama
    r_upd = client.put(
        "/api/jadwal/12",
        json={
            "kelas_id": 1,
            "hari": 3,
            "jam_mulai": "13:00",
            "jam_selesai": "15:00",
            "ruangan_kode": "B201",
            "dosen_id": 1,
        },
        headers=ADMIN_HEADERS,
    )
    assert r_upd.status_code == 200

    r2 = client.get("/api/mahasiswa/2301001/jadwal.ics")
    assert r2.status_code == 200
    assert "UID:jadwal-12@sevima-mini\r\n" in r2.text
    assert "SEQUENCE:1\r\n" in r2.text
    assert "LOCATION:B201\r\n" in r2.text
