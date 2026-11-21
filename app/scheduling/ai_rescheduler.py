"""AI-Powered Rescheduling + 4 Saringan Validasi ("Never Trust, Always Validate").

Prinsip inti (Step 3 & Slide 13-14):
1. Daftar slot tersedia dihitung secara deterministik oleh kode kita sendiri (menggunakan
   fungsi deteksi bentrok Minggu 7), bukan dikarang AI.
2. AI hanya memilih maksimal 3 rekomendasi terbaik dan memberi alasan.
3. Setiap output AI wajib melewati 4 saringan:
   - Saringan 1: Parsing JSON (ambil array antara '[' dan ']'; rusak -> []).
   - Saringan 2: Validasi skema Pydantic ``Saran`` (buang item rusak satu per satu).
   - Saringan 3: Eksistensi ruangan di DB & kapasitas ruangan >= peserta kelas.
   - Saringan 4: Simulasi ``detect_schedule_conflict`` dengan jadwal calon ber-id -1.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Protocol

import httpx
from pydantic import ValidationError

from app.scheduling.conflict import detect_schedule_conflict
from app.scheduling.models import Jadwal, Kelas, Ruangan
from app.scheduling.schemas import Saran

HARI = ["", "Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu"]

# Jam mulai standar kuliah untuk pencarian slot tersedia
JAM_SLOT_STANDAR: tuple[time, ...] = (
    time(8, 0),
    time(10, 0),
    time(13, 0),
    time(15, 0),
)


@dataclass(frozen=True)
class Slot:
    """Slot kandidat yang sudah terverifikasi bebas bentrok dan cukup kapasitas oleh kode."""

    hari: int
    jam_mulai: time
    jam_selesai: time
    ruangan_kode: str
    kapasitas: int


class LLMClient(Protocol):
    """Interface klien LLM agar dapat ditukar dan di-mock dengan FakeLLM di unit test."""

    def complete(self, prompt: str) -> str: ...


class GeminiLLMClient:
    """Klien LLM gratis via Google AI Studio (Gemini Flash) dengan mode JSON & temperature rendah."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.0-flash",
        timeout: float = 15.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def complete(self, prompt: str) -> str:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
            },
        }
        resp = httpx.post(url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]


class OpenRouterLLMClient:
    """Klien LLM alternatif memakai model tier gratis di OpenRouter."""

    def __init__(
        self,
        api_key: str,
        model: str = "google/gemini-2.0-flash-exp:free",
        timeout: float = 15.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def complete(self, prompt: str) -> str:
        resp = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "temperature": 0.1,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


class HeuristicLocalLLMClient:
    """Fallback deterministik lokal bila API key LLM tidak dikonfigurasi.

    Memilih hingga 3 slot terbaik dari daftar ``Available slots`` pada prompt dengan
    prioritas pagi/siang dan kapasitas paling pas (minimal ruang terbuang), lalu
    mengembalikan JSON sesuai kontrak Step 3.
    """

    _SLOT_RE = re.compile(
        r"-\s+(Senin|Selasa|Rabu|Kamis|Jumat|Sabtu)\s+(\d{2}:\d{2})\s+"
        r"(\S+)\s+\(kapasitas\s+(\d+)\)"
    )

    def complete(self, prompt: str) -> str:
        hari_to_idx = {nama: idx for idx, nama in enumerate(HARI) if idx > 0}
        candidates: list[tuple[int, str, str, int]] = []
        for m in self._SLOT_RE.finditer(prompt):
            hari_idx = hari_to_idx[m.group(1)]
            jam = m.group(2)
            ruangan = m.group(3)
            kap = int(m.group(4))
            candidates.append((hari_idx, jam, ruangan, kap))

        # Prioritaskan pagi/siang (08:00, 10:00, 13:00, 15:00), lalu kapasitas paling efisien
        def _rank(item: tuple[int, str, str, int]) -> tuple[int, int, int]:
            hari_idx, jam, _, kap = item
            jam_int = int(jam.split(":")[0])
            prio_waktu = 0 if jam_int <= 10 else (1 if jam_int <= 13 else 2)
            return (prio_waktu, kap, hari_idx)

        candidates.sort(key=_rank)
        top3 = []
        for hari_idx, jam, ruangan, kap in candidates[:3]:
            jam_int = int(jam.split(":")[0])
            sesi = "pagi" if jam_int < 12 else "siang"
            top3.append(
                {
                    "hari": hari_idx,
                    "jam_mulai": jam,
                    "ruangan": ruangan,
                    "reason": (
                        f"Slot {sesi}, ruangan {ruangan} (kapasitas {kap}) mencukupi "
                        f"dan dosen tersedia tanpa bentrok."
                    ),
                }
            )
        return json.dumps(top3, ensure_ascii=False)


def get_default_llm_client() -> LLMClient:
    """Memilih klien LLM aktif berdasarkan environment variable (atau fallback lokal)."""
    if gemini_key := os.getenv("GEMINI_API_KEY"):
        return GeminiLLMClient(api_key=gemini_key)
    if openrouter_key := os.getenv("OPENROUTER_API_KEY"):
        return OpenRouterLLMClient(api_key=openrouter_key)
    return HeuristicLocalLLMClient()


def hitung_durasi(jadwal: Jadwal) -> timedelta:
    return datetime.combine(date.min, jadwal.jam_selesai) - datetime.combine(
        date.min, jadwal.jam_mulai
    )


def hitung_slot_tersedia(
    jadwal: Jadwal,
    peserta: int,
    lain: list[Jadwal],
    ruang: dict[str, Ruangan],
    hari_range: range = range(1, 6),
    jam_pilihan: tuple[time, ...] = JAM_SLOT_STANDAR,
) -> list[Slot]:
    """Menghitung daftar slot tersedia secara deterministik memakai ``detect_schedule_conflict``."""
    durasi = hitung_durasi(jadwal)
    slots: list[Slot] = []

    ruangan_cukup = sorted(
        (r for r in ruang.values() if r.kapasitas >= peserta),
        key=lambda r: (r.kapasitas, r.kode),
    )

    for hari in hari_range:
        for jam_mulai in jam_pilihan:
            selesai_dt = datetime.combine(date.min, jam_mulai) + durasi
            if selesai_dt.date() != date.min:
                continue
            jam_selesai = selesai_dt.time()

            for r in ruangan_cukup:
                # Lewati slot persis seperti posisi bentrok saat ini
                if (
                    hari == jadwal.hari
                    and jam_mulai == jadwal.jam_mulai
                    and r.kode == jadwal.ruangan_kode
                ):
                    continue
                calon = Jadwal(
                    id=-1,
                    kelas_id=jadwal.kelas_id,
                    hari=hari,
                    jam_mulai=jam_mulai,
                    jam_selesai=jam_selesai,
                    ruangan_kode=r.kode,
                    dosen_id=jadwal.dosen_id,
                )
                bentrok = detect_schedule_conflict([*lain, calon])
                if not any(-1 in c.affected for c in bentrok):
                    slots.append(
                        Slot(
                            hari=hari,
                            jam_mulai=jam_mulai,
                            jam_selesai=jam_selesai,
                            ruangan_kode=r.kode,
                            kapasitas=r.kapasitas,
                        )
                    )
    return slots


def bangun_prompt(
    jadwal: Jadwal, kelas: Kelas, peserta: int, slots: list[Slot]
) -> str:
    """Menyusun prompt terstruktur untuk LLM sesuai Step 3 & Slide 13."""
    daftar = "\n".join(
        f"- {HARI[s.hari]} {s.jam_mulai:%H:%M} {s.ruangan_kode} (kapasitas {s.kapasitas})"
        for s in slots
    )
    return (
        "Anda adalah scheduling assistant.\n"
        f"- Jadwal bentrok: {kelas.nama} ({HARI[jadwal.hari]} {jadwal.jam_mulai:%H:%M}, "
        f"Ruang {jadwal.ruangan_kode}, {peserta} mhs, dosen_id={jadwal.dosen_id}).\n"
        f"- Available slots (pilih HANYA dari daftar ini):\n{daftar}\n"
        "Rekomendasikan 3 alternatif: kapasitas cukup, tidak bentrok dengan "
        "jadwal dosen, minimal disruption (prioritas pagi/siang).\n"
        'Balas HANYA JSON: [{"hari": 3, "jam_mulai": "13:00", '
        '"ruangan": "B201", "reason": "..."}]'
    )


def parse_saran(raw: str) -> list[Saran]:
    """Saringan 1 (Parsing JSON) & Saringan 2 (Validasi Skema Pydantic)."""
    start = raw.find("[")
    end = raw.rfind("]")
    if start == -1 or end == -1 or end < start:
        return []
    try:
        items = json.loads(raw[start : end + 1])
    except (ValueError, json.JSONDecodeError):
        return []
    if not isinstance(items, list):
        return []

    hasil: list[Saran] = []
    for item in items:
        try:
            hasil.append(Saran.model_validate(item))
        except ValidationError:
            continue  # Item rusak dibuang satu per satu, item lain tetap diproses
    return hasil


def saring_saran(
    raw: str,
    j: Jadwal,
    peserta: int,
    lain: list[Jadwal],
    ruang: dict[str, Ruangan],
) -> list[Saran]:
    """Menyaring keluaran mentah AI lewat 4 lapisan validasi sebelum tampil ke admin."""
    durasi = hitung_durasi(j)
    valid: list[Saran] = []
    seen: set[tuple[int, time, str]] = set()

    for s in parse_saran(raw):  # Saringan 1 + 2
        # Saringan 3: ruangan ada di DB & kapasitas mencukupi
        r = ruang.get(s.ruangan)
        if r is None or r.kapasitas < peserta:
            continue

        # Hindari duplikat saran identik
        key = (s.hari, s.jam_mulai, s.ruangan)
        if key in seen:
            continue

        selesai_dt = datetime.combine(date.min, s.jam_mulai) + durasi
        if selesai_dt.date() != date.min:
            continue
        selesai = selesai_dt.time()

        # Saringan 4: cek bentrok 3 dimensi memakai fungsi Minggu 7 (calon ber-id -1)
        calon = Jadwal(
            id=-1,
            kelas_id=j.kelas_id,
            hari=s.hari,
            jam_mulai=s.jam_mulai,
            jam_selesai=selesai,
            ruangan_kode=s.ruangan,
            dosen_id=j.dosen_id,
        )
        bentrok = detect_schedule_conflict([*lain, calon])
        if any(-1 in c.affected for c in bentrok):
            continue

        seen.add(key)
        valid.append(s)

    return valid[:3]
