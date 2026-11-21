"""SchedulingService: CRUD jadwal atomik, validasi bentrok & kapasitas, invalidasi KRS,
Transactional Outbox, AI rescheduling tervalidasi, dan ekspor .ics.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.krs.invalidator import KRSInvalidator
from app.krs.models import KRS, KRSDetail, Mahasiswa
from app.scheduling.ai_rescheduler import (
    LLMClient,
    bangun_prompt,
    hitung_durasi,
    hitung_slot_tersedia,
    saring_saran,
)
from app.scheduling.conflict import (
    Conflict,
    ScheduleConflictError,
    cek_kapasitas,
    detect_schedule_conflict,
    hitung_peserta_kelas,
)
from app.scheduling.ical import export_jadwal_ics
from app.scheduling.models import Dosen, Jadwal, Kelas, Outbox, Ruangan
from app.scheduling.observer import EventType, ScheduleEvent
from app.scheduling.outbox import OutboxDispatcher
from app.scheduling.schemas import JadwalIn, Saran

log = logging.getLogger("sevima.scheduling")


class NotFoundError(LookupError):
    """Dilempar jika entitas tidak ditemukan (HTTP 404)."""


def snapshot(jadwal: Jadwal) -> dict[str, Any]:
    """Mengubah objek Jadwal menjadi dictionary siap JSON (jam sebagai 'HH:MM')."""
    return {
        "id": jadwal.id,
        "kelas_id": jadwal.kelas_id,
        "nama_kelas": jadwal.kelas.nama if jadwal.kelas else f"Kelas #{jadwal.kelas_id}",
        "hari": jadwal.hari,
        "jam_mulai": jadwal.jam_mulai.strftime("%H:%M"),
        "jam_selesai": jadwal.jam_selesai.strftime("%H:%M"),
        "ruangan_kode": jadwal.ruangan_kode,
        "dosen_id": jadwal.dosen_id,
        "sequence": jadwal.sequence,
    }


class SchedulingService:
    """Service utama penjadwalan (prinsip satu pintu untuk create/update/delete/apply)."""

    def __init__(
        self,
        db: Session,
        krs: KRSInvalidator,
        dispatcher: OutboxDispatcher | None = None,
    ) -> None:
        self.db = db
        self.krs = krs
        self.dispatcher = dispatcher

    def _kunci(self, ruangan_kode: str, dosen_id: int) -> None:
        """Mengunci baris Ruangan & Dosen secara konsisten untuk mencegah race condition."""
        ruangan = self.db.scalar(
            select(Ruangan).where(Ruangan.kode == ruangan_kode).with_for_update()
        )
        if ruangan is None:
            raise ValueError(f"Ruangan {ruangan_kode} tidak ditemukan")
        dosen = self.db.scalar(
            select(Dosen).where(Dosen.id == dosen_id).with_for_update()
        )
        if dosen is None:
            raise ValueError(f"Dosen {dosen_id} tidak ditemukan")

    def _bentrok_di_db(
        self, data: JadwalIn, abaikan_id: int | None = None
    ) -> list[Conflict]:
        stmt = select(Jadwal).where(Jadwal.hari == data.hari)
        if abaikan_id is not None:
            stmt = stmt.where(Jadwal.id != abaikan_id)
        lain = list(self.db.scalars(stmt))

        calon = Jadwal(
            id=-1,
            kelas_id=data.kelas_id,
            hari=data.hari,
            jam_mulai=data.jam_mulai,
            jam_selesai=data.jam_selesai,
            ruangan_kode=data.ruangan_kode,
            dosen_id=data.dosen_id,
        )
        semua = detect_schedule_conflict([*lain, calon])
        return [c for c in semua if -1 in c.affected]

    def list_jadwal(self) -> list[Jadwal]:
        stmt = (
            select(Jadwal)
            .options(
                joinedload(Jadwal.kelas),
                joinedload(Jadwal.ruangan),
                joinedload(Jadwal.dosen),
            )
            .order_by(Jadwal.hari, Jadwal.jam_mulai, Jadwal.id)
        )
        return list(self.db.scalars(stmt))

    def get_jadwal(self, jadwal_id: int) -> Jadwal:
        stmt = (
            select(Jadwal)
            .options(
                joinedload(Jadwal.kelas),
                joinedload(Jadwal.ruangan),
                joinedload(Jadwal.dosen),
            )
            .where(Jadwal.id == jadwal_id)
        )
        jadwal = self.db.scalar(stmt)
        if jadwal is None:
            raise NotFoundError(f"Jadwal {jadwal_id} tidak ditemukan")
        return jadwal

    def create(self, data: JadwalIn) -> Jadwal:
        jadwal = Jadwal()
        return self._simpan(jadwal, data, before=None, auto_dispatch=False)

    def update(
        self, jadwal_id: int, data: JadwalIn, auto_dispatch: bool = True
    ) -> Jadwal:
        jadwal = self.get_jadwal(jadwal_id)
        before = snapshot(jadwal)
        return self._simpan(jadwal, data, before=before, auto_dispatch=auto_dispatch)

    def _simpan(
        self,
        jadwal: Jadwal,
        data: JadwalIn,
        before: dict[str, Any] | None,
        auto_dispatch: bool = True,
    ) -> Jadwal:
        """Satu transaksi untuk validasi, simpan jadwal, invalidasi KRS, dan insert outbox.

        Dispatcher hanya dijalankan SETELAH ``db.commit()`` berhasil. Kegagalan dispatcher
        tidak pernah membatalkan perubahan jadwal yang sudah ter-commit.
        """
        try:
            self._kunci(data.ruangan_kode, data.dosen_id)
            if konflik := self._bentrok_di_db(data, abaikan_id=jadwal.id):
                raise ScheduleConflictError(konflik)
            cek_kapasitas(self.db, data.kelas_id, data.ruangan_kode)

            for kolom, nilai in data.model_dump().items():
                setattr(jadwal, kolom, nilai)

            if before is None:
                self.db.add(jadwal)
                self.db.flush()
            else:
                # Naikkan nomor SEQUENCE kalender .ics saat jadwal berubah
                jadwal.sequence = (jadwal.sequence or 0) + 1
                # Muat relasi kelas terbaru untuk snapshot yang informatif
                jadwal.kelas = self.db.get(Kelas, data.kelas_id)

                # Langkah baru 1: Invalidasi KRS terdampak (dalam transaksi yang sama)
                self.krs.invalidate(data.kelas_id, "Jadwal berubah")
                if before.get("kelas_id") != data.kelas_id:
                    self.krs.invalidate(int(before["kelas_id"]), "Jadwal berubah")

                # Langkah baru 2: Tulis event ke tabel Outbox (dalam transaksi yang sama)
                event = ScheduleEvent(
                    event_type=EventType.SCHEDULE_CHANGED,
                    jadwal_id=jadwal.id,
                    before=before,
                    after=snapshot(jadwal),
                )
                self.db.add(Outbox.dari_event(event))

            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        self.db.refresh(jadwal)

        # Pengiriman notifikasi HANYA setelah commit berhasil
        if before is not None and auto_dispatch and self.dispatcher is not None:
            try:
                self.dispatcher.run()
            except Exception:
                # Kegagalan dispatcher tidak membatalkan jadwal yang sudah commit
                log.exception(
                    "Dispatcher gagal setelah commit jadwal #%s; baris tetap PENDING di outbox",
                    jadwal.id,
                )

        return jadwal

    def delete(self, jadwal_id: int, auto_dispatch: bool = True) -> None:
        """Menghapus jadwal secara atomik bersama invalidasi KRS & event SCHEDULE_DELETED."""
        jadwal = self.get_jadwal(jadwal_id)
        before = snapshot(jadwal)
        try:
            self.krs.invalidate(jadwal.kelas_id, "Jadwal dihapus")
            self.db.delete(jadwal)
            event = ScheduleEvent(
                event_type=EventType.SCHEDULE_DELETED,
                jadwal_id=jadwal_id,
                before=before,
                after=None,
            )
            self.db.add(Outbox.dari_event(event))
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        if auto_dispatch and self.dispatcher is not None:
            try:
                self.dispatcher.run()
            except Exception:
                log.exception(
                    "Dispatcher gagal setelah delete jadwal #%s; baris tetap PENDING di outbox",
                    jadwal_id,
                )

    def detect_all_conflicts(self) -> list[Conflict]:
        semua_jadwal = self.list_jadwal()
        return detect_schedule_conflict(semua_jadwal)

    def cari_alternatif(self, jadwal_id: int, llm: LLMClient) -> list[Saran]:
        """Menghitung slot tersedia, meminta saran ke LLM, dan menyaring lewat 4 saringan."""
        jadwal = self.get_jadwal(jadwal_id)
        kelas = self.db.get(Kelas, jadwal.kelas_id)
        if kelas is None:
            raise NotFoundError(f"Kelas {jadwal.kelas_id} tidak ditemukan")

        peserta, _ = hitung_peserta_kelas(self.db, jadwal.kelas_id)
        ruang_map = {r.kode: r for r in self.db.scalars(select(Ruangan))}
        lain = list(
            self.db.scalars(select(Jadwal).where(Jadwal.id != jadwal.id))
        )

        # Slot tersedia dihitung kode sendiri (bukan dikarang AI)
        slots = hitung_slot_tersedia(jadwal, peserta, lain, ruang_map)
        prompt = bangun_prompt(jadwal, kelas, peserta, slots)
        raw = llm.complete(prompt)
        return saring_saran(raw, jadwal, peserta, lain, ruang_map)

    def apply_saran(
        self, jadwal_id: int, saran: Saran, auto_dispatch: bool = True
    ) -> Jadwal:
        """Prinsip satu pintu: menerapkan saran AI melalui ``self.update()`` yang sama.

        Jika antara saat saran ditampilkan dan tombol Terapkan ditekan slot sudah diambil
        admin lain, ``update()`` akan mendeteksi bentrok dan melempar ``ScheduleConflictError`` (409).
        """
        jadwal = self.get_jadwal(jadwal_id)
        durasi = hitung_durasi(jadwal)
        selesai_dt = datetime.combine(date.min, saran.jam_mulai) + durasi
        if selesai_dt.date() != date.min:
            raise ValueError("Jam selesai melebihi batas hari")

        data = JadwalIn(
            kelas_id=jadwal.kelas_id,
            hari=saran.hari,
            jam_mulai=saran.jam_mulai,
            jam_selesai=selesai_dt.time(),
            ruangan_kode=saran.ruangan,
            dosen_id=jadwal.dosen_id,
        )
        return self.update(jadwal_id, data, auto_dispatch=auto_dispatch)

    def export_mahasiswa_ics(
        self,
        nim: str,
        awal: date = date(2026, 9, 7),
        akhir: date = date(2026, 12, 18),
    ) -> str:
        """Mengekspor seluruh jadwal mata kuliah yang diambil mahasiswa ke format .ics."""
        mhs = self.db.get(Mahasiswa, nim)
        if mhs is None:
            raise NotFoundError(f"Mahasiswa dengan NIM {nim} tidak ditemukan")

        stmt = (
            select(Jadwal)
            .join(KRSDetail, KRSDetail.kelas_id == Jadwal.kelas_id)
            .join(KRS, KRS.id == KRSDetail.krs_id)
            .options(joinedload(Jadwal.kelas))
            .where(KRS.nim == nim)
            .distinct()
            .order_by(Jadwal.hari, Jadwal.jam_mulai)
        )
        jadwal_list = list(self.db.scalars(stmt))
        items = [
            (j, j.kelas.nama if j.kelas else f"Kelas #{j.kelas_id}")
            for j in jadwal_list
        ]
        return export_jadwal_ics(items, awal=awal, akhir=akhir)
