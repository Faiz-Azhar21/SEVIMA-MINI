"""Model ORM Nilai & Audit Trail (Minggu 9) untuk SEVIMA-Mini."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.akademik import Dosen, KRSDetail


class SkalaNilai(Base):
    """Tabel referensi huruf nilai -> bobot Decimal & status lulus sebagai data."""

    __tablename__ = "skala_nilai"

    huruf: Mapped[str] = mapped_column(String(2), primary_key=True)
    bobot: Mapped[Decimal] = mapped_column(Numeric(3, 2), nullable=False)  # 4.00, bukan float
    lulus: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # baru, Minggu 9


class GradeHistory(Base):
    """Audit trail append-only untuk setiap input dan perubahan nilai."""

    __tablename__ = "grade_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    grade_id: Mapped[int] = mapped_column(Integer, ForeignKey("krs_detail.id"), nullable=False, index=True)
    old_value: Mapped[str | None] = mapped_column(String(2), nullable=True)  # NULL: input awal
    new_value: Mapped[str] = mapped_column(String(2), nullable=False)
    changed_by: Mapped[int] = mapped_column(Integer, ForeignKey("dosen.id"), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    grade: Mapped[KRSDetail] = relationship(back_populates="history")
    pengubah: Mapped[Dosen] = relationship()


VIEW_RIWAYAT_NILAI_SQL = """
CREATE VIEW v_riwayat_nilai AS
SELECT
    h.id AS history_id,
    h.grade_id,
    k.nim,
    k.semester,
    d.kode_mk,
    mk.nama_mk,
    h.old_value,
    h.new_value,
    ds.nama AS pengubah,
    h.changed_at,
    h.reason
FROM grade_history h
JOIN krs_detail d ON d.id = h.grade_id
JOIN krs k ON k.id = d.krs_id
JOIN matakuliah mk ON mk.kode_mk = d.kode_mk
JOIN dosen ds ON ds.id = h.changed_by
"""
