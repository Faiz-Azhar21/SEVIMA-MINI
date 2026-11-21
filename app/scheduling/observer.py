"""Observer Pattern, Strategy Channel, & Idempotency Key (Deliverable 2).

Keputusan desain (dicatat sesuai arahan Materi 4 Minggu 8):
- Menggunakan ``typing.Protocol`` (bukan ABC) untuk ``Observer`` dan ``Channel`` agar
  kelas pengamat/kanal tidak wajib mewarisi kelas induk tertentu (*structural subtyping*),
  sehingga mudah menulis test double (``SpyObserver``, ``RusakObserver``) dan menukar
  kanal notifikasi tanpa menyentuh observer (*Open-Closed Principle*).
- Menggunakan ``@dataclass(frozen=True)`` pada ``ScheduleEvent`` agar event bersifat
  immutable dan tidak dapat diubah diam-diam oleh satu observer bagi observer lain.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol
from uuid import uuid4

log = logging.getLogger("sevima.notifications")

HARI_NAMA = {
    1: "Senin",
    2: "Selasa",
    3: "Rabu",
    4: "Kamis",
    5: "Jumat",
    6: "Sabtu",
}


class EventType(str, Enum):
    SCHEDULE_CHANGED = "SCHEDULE_CHANGED"
    SCHEDULE_DELETED = "SCHEDULE_DELETED"


@dataclass(frozen=True)
class ScheduleEvent:
    """Event immutable yang dipublikasikan ketika jadwal berubah atau dihapus."""

    event_type: EventType
    jadwal_id: int
    before: dict[str, Any] | None  # None untuk jadwal baru
    after: dict[str, Any] | None  # None jika jadwal dihapus
    event_id: str = field(default_factory=lambda: uuid4().hex)


class Observer(Protocol):
    """Kontrak pengamat perubahan jadwal."""

    def update(self, event: ScheduleEvent) -> None: ...


class IdemStore(Protocol):
    """Penyimpanan kunci idempotensi untuk mencegah pengiriman ganda saat retry."""

    def sudah(self, key: str) -> bool: ...
    def catat(self, key: str) -> None: ...


class InMemoryIdemStore:
    """Implementasi IdemStore dalam memori (satu kunci hanya terkirim sekali)."""

    def __init__(self) -> None:
        self._keys: set[str] = set()

    def sudah(self, key: str) -> bool:
        return key in self._keys

    def catat(self, key: str) -> None:
        self._keys.add(key)

    def clear(self) -> None:
        self._keys.clear()


class Channel(Protocol):
    """Kontrak kanal notifikasi (mirip Strategy Pattern)."""

    nama: str

    def send(self, penerima: str, pesan: str, key: str) -> None: ...


class LogChannel:
    """Simulasi kanal EMAIL/SMS/PUSH lewat logging + opsional log_sink untuk UI/demo."""

    def __init__(
        self,
        nama: str,
        store: IdemStore,
        log_sink: list[dict[str, Any]] | None = None,
    ) -> None:
        self.nama = nama
        self.store = store
        self.log_sink = log_sink

    def send(self, penerima: str, pesan: str, key: str) -> None:
        if self.store.sudah(key):
            return
        log.info("[%s] ke %s: %s", self.nama, penerima, pesan)
        if self.log_sink is not None:
            self.log_sink.append(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "channel": self.nama,
                    "penerima": penerima,
                    "pesan": pesan,
                    "idempotency_key": key,
                }
            )
        self.store.catat(key)


class PesertaRepo(Protocol):
    """Kontrak repositori untuk mencari daftar NIM mahasiswa peserta suatu kelas."""

    def nim_by_kelas(self, kelas_id: int) -> list[str]: ...


class DosenRepo(Protocol):
    """Kontrak repositori untuk mencari kontak/nama dosen berdasarkan ID."""

    def kontak_by_id(self, dosen_id: int) -> str: ...


def _fmt_slot(data: dict[str, Any]) -> str:
    hari_str = HARI_NAMA.get(int(data.get("hari", 0)), f"Hari-{data.get('hari')}")
    jam_mulai = data.get("jam_mulai", "?")
    jam_selesai = data.get("jam_selesai", "?")
    ruangan = data.get("ruangan_kode", "?")
    return f"{hari_str} {jam_mulai}-{jam_selesai} ({ruangan})"


def ringkas(event: ScheduleEvent) -> str:
    """Menyusun ringkasan pesan perubahan jadwal yang mudah dibaca stakeholder."""
    if event.event_type == EventType.SCHEDULE_DELETED:
        ref = event.before or {}
        nama_mk = ref.get("nama_kelas", f"Kelas #{ref.get('kelas_id', '?')}")
        return f"Jadwal #{event.jadwal_id} ({nama_mk}) DIHAPUS dari {_fmt_slot(ref)}"

    after = event.after or {}
    before = event.before
    nama_mk = after.get("nama_kelas", f"Kelas #{after.get('kelas_id', '?')}")
    if before:
        return (
            f"Jadwal #{event.jadwal_id} ({nama_mk}) berubah: "
            f"{_fmt_slot(before)} -> {_fmt_slot(after)}"
        )
    return f"Jadwal #{event.jadwal_id} ({nama_mk}) dijadwalkan pada {_fmt_slot(after)}"


class ScheduleSubject:
    """Publisher / NotificationManager untuk event perubahan jadwal.

    Ciri ketahanan:
    - ``attach()`` menolak duplikasi observer (mencegah notifikasi berlipat).
    - ``notify()`` mengiterasi salinan daftar observer sehingga aman bila ada ``detach()``
      saat iterasi.
    - Setiap panggilan ``observer.update(event)`` dibungkus ``try/except`` agar kegagalan
      satu observer tidak menghentikan observer lainnya.
    """

    def __init__(self) -> None:
        self._observers: list[Observer] = []

    @property
    def observers(self) -> list[Observer]:
        return list(self._observers)

    def attach(self, observer: Observer) -> None:
        if observer not in self._observers:
            self._observers.append(observer)

    def detach(self, observer: Observer) -> None:
        if observer in self._observers:
            self._observers.remove(observer)

    def notify(self, event: ScheduleEvent) -> list[str]:
        gagal: list[str] = []
        for observer in list(self._observers):  # iterasi atas salinan
            try:
                observer.update(event)
            except Exception:
                log.exception(
                    "Observer %s gagal untuk %s",
                    type(observer).__name__,
                    event.event_id,
                )
                gagal.append(type(observer).__name__)
        return gagal


# Alias agar penamaan di dokumen tugas (NotificationManager) dan video (ScheduleSubject) konsisten
NotificationManager = ScheduleSubject


class StudentObserver:
    """Mengirim notifikasi ke seluruh mahasiswa peserta kelas terdampak."""

    def __init__(self, peserta: PesertaRepo, channels: list[Channel]) -> None:
        self.peserta = peserta
        self.channels = channels

    def update(self, event: ScheduleEvent) -> None:
        data = event.after or event.before
        if not data:
            return
        pesan = ringkas(event)
        kelas_ids = {int(data["kelas_id"])}
        if event.before and event.before.get("kelas_id") is not None:
            kelas_ids.add(int(event.before["kelas_id"]))

        penerima_nims: list[str] = []
        seen: set[str] = set()
        for kid in sorted(kelas_ids):
            for nim in self.peserta.nim_by_kelas(kid):
                if nim not in seen:
                    seen.add(nim)
                    penerima_nims.append(nim)

        for nim in penerima_nims:
            for ch in self.channels:
                ch.send(nim, pesan, key=f"{event.event_id}:{nim}:{ch.nama}")


class LecturerObserver:
    """Mengirim notifikasi ke dosen pengampu (termasuk dosen lama jika diganti)."""

    def __init__(self, dosen_repo: DosenRepo, channels: list[Channel]) -> None:
        self.dosen_repo = dosen_repo
        self.channels = channels

    def update(self, event: ScheduleEvent) -> None:
        pesan = ringkas(event)
        dosen_ids: list[int] = []
        if event.after and event.after.get("dosen_id") is not None:
            dosen_ids.append(int(event.after["dosen_id"]))
        if event.before and event.before.get("dosen_id") is not None:
            old_id = int(event.before["dosen_id"])
            if old_id not in dosen_ids:
                dosen_ids.append(old_id)

        for dosen_id in dosen_ids:
            kontak = self.dosen_repo.kontak_by_id(dosen_id)
            for ch in self.channels:
                ch.send(
                    kontak,
                    pesan,
                    key=f"{event.event_id}:dosen-{dosen_id}:{ch.nama}",
                )


class AdminObserver:
    """Mengirim ringkasan jejak perubahan jadwal ke Admin Akademik."""

    def __init__(
        self,
        channels: list[Channel],
        admin_kontak: str = "admin-akademik@sevima-mini.ac.id",
    ) -> None:
        self.channels = channels
        self.admin_kontak = admin_kontak

    def update(self, event: ScheduleEvent) -> None:
        pesan = f"[AUDIT ADMIN] {ringkas(event)}"
        for ch in self.channels:
            ch.send(
                self.admin_kontak,
                pesan,
                key=f"{event.event_id}:admin:{ch.nama}",
            )
