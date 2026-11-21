"""Invalidasi KRS terdampak saat jadwal berubah/dihapus (Deliverable 4)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.krs.models import Actor, KRS, KRSDetail, KRSStatus


class KRSInvalidator:
    """Mengembalikan KRS berstatus SUBMITTED/APPROVED yang mengambil kelas terdampak ke REVISION.

    Catatan desain:
    - KRS berstatus DRAFT dan REVISION tidak disentuh karena akan dicek ulang saat submit.
    - Tidak pernah memanggil ``db.commit()`` sendiri agar tetap atomik dalam transaksi
      milik ``SchedulingService``.
    - Selalu mengubah status melalui ``krs.transition(..., Actor.SISTEM)`` (prinsip satu pintu).
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def invalidate(self, kelas_id: int, alasan: str) -> list[KRS]:
        stmt = (
            select(KRS)
            .join(KRSDetail, KRSDetail.krs_id == KRS.id)
            .where(
                KRSDetail.kelas_id == kelas_id,
                KRS.status.in_([KRSStatus.SUBMITTED, KRSStatus.APPROVED]),
            )
            .distinct()
            .with_for_update()
        )
        terdampak = list(self.db.scalars(stmt))
        for krs in terdampak:
            krs.transition(KRSStatus.REVISION, Actor.SISTEM)
            krs.catatan_revisi = f"Otomatis: {alasan}"
        return terdampak
