"""Demo singkat Minggu 8 (sesuai panduan demo & Viva pada Slide 18).

Menjalankan alur lengkap tanpa server eksternal (SQLite in-memory):
1. Menampilkan konflik jadwal awal (room_conflict & lecturer_conflict).
2. Meminta saran alternatif AI (divalidasi 4 saringan) untuk Jadwal #12 (PBO).
3. Menerapkan saran alternatif melalui satu pintu ``SchedulingService.update()``.
4. Menunjukkan baris Outbox (``SENT``) dan log simulasi 3 kanal (``EMAIL``, ``SMS``, ``PUSH``).
5. Menunjukkan status KRS terdampak berubah dari ``APPROVED``/``SUBMITTED`` ke ``REVISION``
   sementara ``DRAFT`` dan ``REVISION`` lama tidak disentuh.
6. Menampilkan hasil ekspor iCalendar (``.ics``) mahasiswa dengan ``SEQUENCE:1``.
"""

from __future__ import annotations

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.krs.invalidator import KRSInvalidator
from app.krs.models import KRS
from app.main import wire_observers
from app.scheduling.ai_rescheduler import HeuristicLocalLLMClient
from app.scheduling.models import Outbox
from app.scheduling.outbox import OutboxDispatcher
from app.scheduling.service import SchedulingService
from app.seed import seed_demo_data


def main() -> None:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    db = session_factory()
    try:
        seed_demo_data(db)
        log_sink: list[dict] = []
        subject, _ = wire_observers(session_factory, log_sink=log_sink)
        dispatcher = OutboxDispatcher(db=db, subject=subject)
        svc = SchedulingService(db=db, krs=KRSInvalidator(db), dispatcher=dispatcher)

        print("=" * 72)
        print("1. KONFLIK JADWAL AWAL")
        print("=" * 72)
        for c in svc.detect_all_conflicts():
            print(f"  - [{c.type}] affected={c.affected} | {c.detail}")

        print("\n" + "=" * 72)
        print("2. STATUS KRS SEBELUM PERUBAHAN JADWAL")
        print("=" * 72)
        for krs in db.scalars(select(KRS).order_by(KRS.id)):
            print(f"  - NIM {krs.nim}: {krs.status.value:9s} | catatan={krs.catatan_revisi}")

        print("\n" + "=" * 72)
        print("3. SARAN ALTERNATIF AI (LOLOS 4 SARINGAN) UNTUK JADWAL #12 (PBO)")
        print("=" * 72)
        saran_list = svc.cari_alternatif(12, HeuristicLocalLLMClient())
        for idx, s in enumerate(saran_list, 1):
            print(f"  {idx}. Hari={s.hari} Jam={s.jam_mulai:%H:%M} Ruang={s.ruangan} | {s.reason}")

        print("\n" + "=" * 72)
        print("4. TERAPKAN SARAN #1 VIA SATU PINTU (SchedulingService.update)")
        print("=" * 72)
        updated = svc.apply_saran(12, saran_list[0])
        print(
            f"  Jadwal #{updated.id} dipindahkan -> Hari={updated.hari}, "
            f"{updated.jam_mulai:%H:%M}-{updated.jam_selesai:%H:%M}, "
            f"Ruang={updated.ruangan_kode}, SEQUENCE={updated.sequence}"
        )

        print("\n" + "=" * 72)
        print("5. TABEL OUTBOX & SIMULASI LOG 3 KANAL (EMAIL / SMS / PUSH)")
        print("=" * 72)
        for row in db.scalars(select(Outbox).order_by(Outbox.id)):
            print(
                f"  Outbox #{row.id}: event_id={row.event_id} "
                f"status={row.status} attempts={row.attempts}"
            )
        print(f"  Total notifikasi terkirim: {len(log_sink)} (sampel 9 baris pertama):")
        for entry in log_sink[:9]:
            print(f"    [{entry['channel']:5s}] ke {entry['penerima']}: {entry['pesan']}")

        print("\n" + "=" * 72)
        print("6. STATUS KRS SESUDAH PERUBAHAN JADWAL")
        print("=" * 72)
        db.expire_all()
        for krs in db.scalars(select(KRS).order_by(KRS.id)):
            print(f"  - NIM {krs.nim}: {krs.status.value:9s} | catatan={krs.catatan_revisi}")

        print("\n" + "=" * 72)
        print("7. EKSPOR KALENDER .ICS RINA (NIM 2301001) — RFC 5545 CRLF")
        print("=" * 72)
        ics = svc.export_mahasiswa_ics("2301001")
        print(ics)
    finally:
        db.close()


if __name__ == "__main__":
    main()
