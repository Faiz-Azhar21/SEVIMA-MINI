"""Repository tipis untuk membaca data nilai, skala nilai, dan view riwayat."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.domain.gpa import DUA_DESIMAL, NilaiRecord, Skala
from app.models.akademik import KRS, KRSDetail, MataKuliah
from app.models.nilai import SkalaNilai


@dataclass(frozen=True)
class RiwayatNilaiRow:
    """Satu baris hasil query view v_riwayat_nilai."""

    history_id: int
    grade_id: int
    nim: str
    semester: str
    kode_mk: str
    nama_mk: str
    old_value: str | None
    new_value: str
    pengubah: str
    changed_at: str
    reason: str | None


class NilaiRepo:
    """Repository untuk akses data nilai memakai SQLAlchemy 2.0 select()."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def records(self, nim: str) -> list[NilaiRecord]:
        """Ambil seluruh record nilai mahasiswa yang sudah terisi (nilai IS NOT NULL)."""
        stmt = (
            select(
                KRSDetail.kode_mk,
                KRS.semester,
                MataKuliah.sks,
                KRSDetail.nilai,
            )
            .join(KRS, KRSDetail.krs_id == KRS.id)
            .join(MataKuliah, KRSDetail.kode_mk == MataKuliah.kode_mk)
            .where(KRS.nim == nim, KRSDetail.nilai.is_not(None))
        )
        return [NilaiRecord(*row) for row in self.db.execute(stmt)]

    def skala(self) -> dict[str, Skala]:
        """Baca tabel skala_nilai menjadi kamus huruf -> Skala(bobot Decimal, lulus bool)."""
        return {
            s.huruf: Skala(
                bobot=Decimal(str(s.bobot)).quantize(DUA_DESIMAL, rounding=ROUND_HALF_UP),
                lulus=bool(s.lulus),
            )
            for s in self.db.scalars(select(SkalaNilai))
        }

    def riwayat_nilai(self, nim: str) -> list[RiwayatNilaiRow]:
        """Baca riwayat perubahan nilai per mahasiswa dari SQL view v_riwayat_nilai."""
        stmt = text(
            """
            SELECT history_id, grade_id, nim, semester, kode_mk, nama_mk,
                   old_value, new_value, pengubah, changed_at, reason
            FROM v_riwayat_nilai
            WHERE nim = :nim
            ORDER BY changed_at DESC, history_id DESC
            """
        )
        rows = self.db.execute(stmt, {"nim": nim}).mappings().all()
        return [
            RiwayatNilaiRow(
                history_id=int(row["history_id"]),
                grade_id=int(row["grade_id"]),
                nim=str(row["nim"]),
                semester=str(row["semester"]),
                kode_mk=str(row["kode_mk"]),
                nama_mk=str(row["nama_mk"]),
                old_value=row["old_value"],
                new_value=str(row["new_value"]),
                pengubah=str(row["pengubah"]),
                changed_at=str(row["changed_at"]),
                reason=row["reason"],
            )
            for row in rows
        ]

    def calculate_ipk_sql(self, nim: str) -> Decimal:
        """Versi SQL opsional (CTE + Window Function) untuk bahan differential testing.

        Pembulatan ROUND_HALF_UP tetap dilakukan sekali di Python memakai Decimal
        agar tidak terpengaruh float SQLite / banker's rounding.
        """
        stmt = text(
            """
            WITH terbaik AS (
                SELECT kd.kode_mk,
                       mk.sks,
                       s.bobot,
                       s.lulus,
                       ROW_NUMBER() OVER (
                           PARTITION BY kd.kode_mk
                           ORDER BY s.bobot DESC
                       ) AS rn
                FROM krs_detail kd
                JOIN krs k ON k.id = kd.krs_id
                JOIN matakuliah mk ON mk.kode_mk = kd.kode_mk
                JOIN skala_nilai s ON s.huruf = kd.nilai
                WHERE k.nim = :nim AND kd.nilai IS NOT NULL
            )
            SELECT
                COALESCE(SUM(ROUND(bobot * 100) * sks), 0) AS total_mutu_x100,
                COALESCE(SUM(sks), 0) AS total_sks,
                COALESCE(SUM(bobot * sks) * 1.0 / NULLIF(SUM(sks), 0), 0) AS raw_ipk
            FROM terbaik
            WHERE rn = 1 AND lulus = 1
            """
        )
        row = self.db.execute(stmt, {"nim": nim}).mappings().one()
        total_sks = int(row["total_sks"])
        if total_sks == 0:
            return Decimal("0.00")
        total_mutu_x100 = Decimal(str(int(round(row["total_mutu_x100"]))))
        return (total_mutu_x100 / Decimal(total_sks * 100)).quantize(
            DUA_DESIMAL, rounding=ROUND_HALF_UP
        )
