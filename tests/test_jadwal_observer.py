"""Pengujian inti Minggu 8 (Deliverable 5 · Slide 17):
1. Observer dipanggil tepat sekali (dedup attach) & tahan gagal (try/except per observer).
2. Urutan COMMIT sebelum notify (rollback tidak mengirim notifikasi) + retry idempotency.
3. Integration test: update/delete jadwal -> invalidasi KRS ke REVISION + baris Outbox + 3 kanal log.
4. Saringan saran AI (4 lapisan validasi) secara deterministik memakai FakeLLM.
"""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from datetime import time

import pytest
from sqlalchemy import func, select

from app.krs.models import KRS, KRSStatus
from app.scheduling.conflict import ScheduleConflictError
from app.scheduling.models import Jadwal, Outbox
from app.scheduling.observer import (
    EventType,
    InMemoryIdemStore,
    LogChannel,
    ScheduleEvent,
    ScheduleSubject,
    StudentObserver,
)
from app.scheduling.outbox import OutboxDispatcher
from app.scheduling.schemas import JadwalIn


class SpyObserver:
    def __init__(self) -> None:
        self.events: list[ScheduleEvent] = []

    def update(self, event: ScheduleEvent) -> None:
        self.events.append(event)


class RusakObserver:
    def update(self, event: ScheduleEvent) -> None:
        raise RuntimeError("server SMS mati")


class FakeLLM:
    def __init__(self, balasan: str) -> None:
        self.balasan = balasan
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.balasan


# --- TEST 1 & 2 (Slide 17): Sekali, tahan gagal, tanpa database ---


def test_notify_sekali_dan_tahan_gagal():
    """Observer yang di-attach 2x hanya dipanggil sekali; observer rusak tidak hentikan yg lain."""
    subject, spy = ScheduleSubject(), SpyObserver()
    subject.attach(RusakObserver())
    subject.attach(spy)
    subject.attach(spy)  # dobel: diabaikan

    gagal = subject.notify(ScheduleEvent(EventType.SCHEDULE_CHANGED, 1, {}, {}))
    assert len(spy.events) == 1
    assert gagal == ["RusakObserver"]


def test_schedule_event_immutable():
    """ScheduleEvent bersifat frozen sehingga tidak bisa dimutasi observer."""
    ev = ScheduleEvent(EventType.SCHEDULE_CHANGED, 12, {"hari": 1}, {"hari": 3})
    with pytest.raises(FrozenInstanceError):
        ev.jadwal_id = 99  # type: ignore[misc]


def test_detach_saat_notify_tidak_merusak_iterasi():
    """Iterasi di notify memakai salinan daftar sehingga detach di tengah loop aman."""
    subject = ScheduleSubject()
    spy = SpyObserver()

    class SelfDetachingObserver:
        def __init__(self) -> None:
            self.called = 0

        def update(self, event: ScheduleEvent) -> None:
            self.called += 1
            subject.detach(self)

    self_det = SelfDetachingObserver()
    subject.attach(self_det)
    subject.attach(spy)

    ev = ScheduleEvent(EventType.SCHEDULE_CHANGED, 1, {}, {})
    subject.notify(ev)
    subject.notify(ev)

    assert self_det.called == 1
    assert len(spy.events) == 2


# --- TEST 3 (Slide 17): Integration test update jadwal -> KRS REVISION + Outbox + 3 kanal ---


def test_update_invalidasi_krs(service_bundle):
    """Mengubah jadwal PBO (#12) memindahkan KRS APPROVED (Rina) & SUBMITTED (Doni)
    ke REVISION, membiarkan DRAFT (Siti), menulis 1 Outbox SENT, dan mencatat 3 kanal.
    """
    svc = service_bundle["svc"]
    db = service_bundle["db"]
    logs = service_bundle["logs"]

    svc.update(
        12,
        JadwalIn(
            kelas_id=1,
            hari=3,
            jam_mulai=time(13, 0),
            jam_selesai=time(15, 0),
            ruangan_kode="B201",
            dosen_id=1,
        ),
    )

    db.expire_all()
    krs_rina = db.scalar(select(KRS).where(KRS.nim == "2301001"))
    krs_doni = db.scalar(select(KRS).where(KRS.nim == "2301002"))
    krs_siti = db.scalar(select(KRS).where(KRS.nim == "2301003"))
    jadwal_12 = db.get(Jadwal, 12)

    assert krs_rina is not None and krs_rina.status == KRSStatus.REVISION
    assert krs_doni is not None and krs_doni.status == KRSStatus.REVISION
    assert krs_siti is not None and krs_siti.status == KRSStatus.DRAFT
    assert jadwal_12 is not None and jadwal_12.sequence == 1

    # Tepat 1 baris outbox tertulis dan berstatus SENT
    assert db.scalar(select(func.count()).select_from(Outbox)) == 1
    outbox_row = db.scalar(select(Outbox))
    assert outbox_row is not None and outbox_row.status == "SENT"
    assert outbox_row.attempts == 1

    # Ketiga kanal EMAIL, SMS, PUSH tercatat untuk mahasiswa, dosen, dan admin
    channels_seen = {entry["channel"] for entry in logs}
    assert channels_seen == {"EMAIL", "SMS", "PUSH"}
    penerima_seen = {entry["penerima"] for entry in logs}
    assert "2301001" in penerima_seen  # Mahasiswa Rina
    assert any("budi@sevima-mini.ac.id" in p for p in penerima_seen)  # Dosen Dr. Budi
    assert "admin-akademik@sevima-mini.ac.id" in penerima_seen  # Admin


def test_ganti_dosen_notifikasi_dosen_lama_dan_baru(service_bundle):
    """Jika dosen pengampu diganti, baik dosen baru maupun dosen lama menerima notifikasi."""
    svc = service_bundle["svc"]
    logs = service_bundle["logs"]

    # Jadwal #12 awalnya dosen_id=1 (Dr. Budi), diganti ke dosen_id=2 (Dr. Sari)
    svc.update(
        12,
        JadwalIn(
            kelas_id=1,
            hari=3,
            jam_mulai=time(13, 0),
            jam_selesai=time(15, 0),
            ruangan_kode="B201",
            dosen_id=2,
        ),
    )
    penerima = {entry["penerima"] for entry in logs}
    assert any("budi@sevima-mini.ac.id" in p for p in penerima)
    assert any("sari@sevima-mini.ac.id" in p for p in penerima)


def test_delete_jadwal_invalidasi_krs_dan_outbox_deleted(service_bundle):
    """Menghapus jadwal menginvalidasi KRS terdampak dan mencatat event SCHEDULE_DELETED."""
    svc = service_bundle["svc"]
    db = service_bundle["db"]
    logs = service_bundle["logs"]

    svc.delete(12)
    db.expire_all()
    assert db.get(Jadwal, 12) is None
    krs_rina = db.scalar(select(KRS).where(KRS.nim == "2301001"))
    assert krs_rina is not None and krs_rina.status == KRSStatus.REVISION

    row = db.scalar(select(Outbox))
    assert row is not None
    assert row.payload["type"] == EventType.SCHEDULE_DELETED.value
    assert row.payload["after"] is None
    assert row.status == "SENT"
    assert any("DIHAPUS" in l["pesan"] for l in logs)


def test_commit_sebelum_notify_dan_rollback_tidak_kirim(service_bundle, monkeypatch):
    """Membuktikan COMMIT terjadi SEBELUM notify, dan rollback menghasilkan 0 notifikasi."""
    svc = service_bundle["svc"]
    db = service_bundle["db"]
    subject = service_bundle["subject"]
    logs = service_bundle["logs"]

    # 1. Percobaan update bentrok (Kamis 08:00 C301 sudah diisi Jadwal #25) -> rollback!
    with pytest.raises(ScheduleConflictError):
        svc.update(
            12,
            JadwalIn(
                kelas_id=1,
                hari=4,
                jam_mulai=time(8, 0),
                jam_selesai=time(10, 0),
                ruangan_kode="C301",
                dosen_id=1,
            ),
        )
    assert db.scalar(select(func.count()).select_from(Outbox)) == 0
    assert len(logs) == 0

    # 2. Catat urutan eksekusi commit vs notify pada update yang sah
    urutan: list[str] = []
    orig_commit = db.commit
    orig_notify = subject.notify

    def _wrapped_commit():
        urutan.append("COMMIT")
        return orig_commit()

    def _wrapped_notify(event):
        urutan.append("NOTIFY")
        return orig_notify(event)

    monkeypatch.setattr(db, "commit", _wrapped_commit)
    monkeypatch.setattr(subject, "notify", _wrapped_notify)

    svc.update(
        12,
        JadwalIn(
            kelas_id=1,
            hari=3,
            jam_mulai=time(13, 0),
            jam_selesai=time(15, 0),
            ruangan_kode="B201",
            dosen_id=1,
        ),
    )
    assert urutan.index("COMMIT") < urutan.index("NOTIFY")


def test_outbox_retry_idempotency_tanpa_duplikat_dan_max_attempts(db):
    """Jika 1 observer gagal, outbox tetap PENDING; saat retry sukses, observer yg sudah
    berhasil tidak mengirim pesan ganda berkat kunci idempotensi. Jika gagal 5x -> FAILED.
    """
    store = InMemoryIdemStore()
    sent_logs: list[dict] = []
    channels = [LogChannel(n, store=store, log_sink=sent_logs) for n in ("EMAIL", "SMS")]

    class FakePeserta:
        def nim_by_kelas(self, kelas_id: int) -> list[str]:
            return ["2301001"]

    class FlakyObserver:
        def __init__(self) -> None:
            self.should_fail = True

        def update(self, event: ScheduleEvent) -> None:
            if self.should_fail:
                raise RuntimeError("gateway sementara down")

    flaky = FlakyObserver()
    subject = ScheduleSubject()
    subject.attach(StudentObserver(FakePeserta(), channels))
    subject.attach(flaky)

    ev = ScheduleEvent(
        EventType.SCHEDULE_CHANGED,
        12,
        {"kelas_id": 1, "hari": 1, "jam_mulai": "08:00", "jam_selesai": "10:00", "ruangan_kode": "A101"},
        {"kelas_id": 1, "hari": 3, "jam_mulai": "13:00", "jam_selesai": "15:00", "ruangan_kode": "B201"},
    )
    db.add(Outbox.dari_event(ev))
    db.commit()

    dispatcher = OutboxDispatcher(db=db, subject=subject)

    # Percobaan 1: StudentObserver sukses (2 pesan), FlakyObserver gagal -> tetap PENDING
    dispatcher.run()
    row = db.scalar(select(Outbox))
    assert row is not None and row.status == "PENDING" and row.attempts == 1
    assert len(sent_logs) == 2

    # Percobaan 2: FlakyObserver pulih -> status SENT, StudentObserver TIDAK kirim ganda!
    flaky.should_fail = False
    dispatcher.run()
    db.refresh(row)
    assert row.status == "SENT" and row.attempts == 2
    assert len(sent_logs) == 2  # Tetap 2 (bukan 4) berkat IdemStore!

    # Uji MAX_ATTEMPTS = 5 -> FAILED
    ev2 = ScheduleEvent(EventType.SCHEDULE_CHANGED, 15, {}, {"kelas_id": 2})
    db.add(Outbox.dari_event(ev2))
    db.commit()
    flaky.should_fail = True
    for _ in range(OutboxDispatcher.MAX_ATTEMPTS):
        dispatcher.run()
    row2 = db.scalar(select(Outbox).where(Outbox.event_id == ev2.event_id))
    assert row2 is not None and row2.status == "FAILED" and row2.attempts == 5


# --- TEST 4 (Slide 17): Saringan saran AI dengan FakeLLM (tanpa API sungguhan) ---


def test_saran_ai_disaring(service_bundle):
    """FakeLLM mengembalikan 3 saran: 1 valid, 1 ruangan fiktif, 1 bentrok -> lolos tepat 1."""
    svc = service_bundle["svc"]
    # Jadwal #12 (PBO, 40 mhs, dosen_id=1)
    # - Hari 3 13:00 B201 (kap 45) -> VALID
    # - Hari 2 10:00 Z999 -> RUANGAN FIKTIF (ditolak Saringan 3)
    # - Hari 4 08:00 C301 -> BENTROK dengan Jadwal #25 (ditolak Saringan 4)
    palsu = FakeLLM(
        json.dumps(
            [
                {"hari": 3, "jam_mulai": "13:00", "ruangan": "B201", "reason": "kosong"},
                {"hari": 2, "jam_mulai": "10:00", "ruangan": "Z999", "reason": "fiktif"},
                {"hari": 4, "jam_mulai": "08:00", "ruangan": "C301", "reason": "bentrok"},
            ]
        )
    )
    hasil = svc.cari_alternatif(12, palsu)
    assert [(s.hari, s.ruangan) for s in hasil] == [(3, "B201")]


def test_saran_ai_empat_saringan_edge_cases(service_bundle):
    """Menguji ketahanan 4 saringan terhadap teks pembuka, JSON rusak, skema invalid,
    ruangan terlalu kecil, dan batas maksimum 3 saran.
    """
    svc = service_bundle["svc"]

    # 1. Bukan JSON sama sekali -> [] (tidak crash)
    assert svc.cari_alternatif(12, FakeLLM("Maaf, saya tidak tahu.")) == []

    # 2. Teks pembuka + item skema rusak + ruangan kapasitas kecil (LAB1 kap. 25 < 40) + 4 saran valid
    raw_campuran = (
        "Berikut rekomendasi terbaik:\n"
        + json.dumps(
            [
                {"hari": 9, "jam_mulai": "08:00", "ruangan": "B201", "reason": "hari invalid"},
                {"hari": 3, "jam_mulai": "08:00", "ruangan": "LAB1", "reason": "terlalu kecil"},
                {"hari": 3, "jam_mulai": "08:00", "ruangan": "B201", "reason": "valid 1"},
                {"hari": 3, "jam_mulai": "10:00", "ruangan": "B201", "reason": "valid 2"},
                {"hari": 5, "jam_mulai": "08:00", "ruangan": "C301", "reason": "valid 3"},
                {"hari": 5, "jam_mulai": "10:00", "ruangan": "C301", "reason": "valid 4"},
            ]
        )
        + "\nSemoga membantu!"
    )
    hasil = svc.cari_alternatif(12, FakeLLM(raw_campuran))
    assert len(hasil) == 3  # Maksimal 3
    assert all(s.ruangan != "LAB1" for s in hasil)
    assert [(s.hari, s.jam_mulai.strftime("%H:%M"), s.ruangan) for s in hasil] == [
        (3, "08:00", "B201"),
        (3, "10:00", "B201"),
        (5, "08:00", "C301"),
    ]
