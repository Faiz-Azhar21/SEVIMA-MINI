"""OutboxDispatcher: mengirim notifikasi SETELAH transaksi database commit."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.scheduling.models import Outbox
from app.scheduling.observer import ScheduleSubject


class OutboxDispatcher:
    """Memproses baris outbox berstatus PENDING secara aman (at-least-once + dedup).

    - Menggunakan ``with_for_update(skip_locked=True)`` supaya dua dispatcher yang berjalan
      bersamaan tidak mengambil baris yang sama (di PostgreSQL; no-op aman di SQLite).
    - Jika ada observer gagal, baris tetap ``PENDING`` untuk dicoba ulang sampai
      ``MAX_ATTEMPTS`` (5 kali), lalu ditandai ``FAILED`` agar diperiksa admin.
    - Deduplikasi pesan saat retry ditangani oleh kunci idempotensi di tiap ``Channel``.
    """

    MAX_ATTEMPTS = 5

    def __init__(self, db: Session, subject: ScheduleSubject) -> None:
        self.db = db
        self.subject = subject

    def run(self, batch: int = 50) -> int:
        stmt = (
            select(Outbox)
            .where(Outbox.status == "PENDING")
            .order_by(Outbox.id)
            .limit(batch)
            .with_for_update(skip_locked=True)
        )
        rows = list(self.db.scalars(stmt))
        if not rows:
            return 0

        for row in rows:
            row.attempts += 1
            gagal = self.subject.notify(row.ke_event())
            if not gagal:
                row.status = "SENT"
            elif row.attempts >= self.MAX_ATTEMPTS:
                row.status = "FAILED"  # Admin periksa

        self.db.commit()
        return len(rows)
