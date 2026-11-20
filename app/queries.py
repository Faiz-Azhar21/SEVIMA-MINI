"""Complex SQL queries yang dioptimasi dengan composite index (Step 3)."""

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class UnmetPrerequisite:
    """Representasi mata kuliah prasyarat yang belum terpenuhi."""

    kode_mk: str
    nama: str
    nilai_minimal: str


# Query SQL Step 3:
# Memanfaatkan:
# 1. idx_prerequisite_kode_mk(kode_mk, prasyarat_kode_mk, nilai_minimal)
# 2. idx_riwayat_nilai_nim_mk_sem(nim, kode_mk, semester, nilai_huruf)
# sehingga subquery EXISTS dapat diselesaikan via index-only scan.
UNMET_PREREQUISITES_SQL = text(
    """
    SELECT
        p.prasyarat_kode_mk AS kode_mk,
        m.nama AS nama,
        COALESCE(p.nilai_minimal, 'C') AS nilai_minimal
    FROM prerequisite p
    JOIN matakuliah m ON m.kode_mk = p.prasyarat_kode_mk
    WHERE p.kode_mk = :kode_mk
      AND NOT EXISTS (
          SELECT 1
          FROM riwayat_nilai rn
          WHERE rn.nim = :nim
            AND rn.kode_mk = p.prasyarat_kode_mk
            AND rn.semester < :semester_sekarang
            AND CASE rn.nilai_huruf
                  WHEN 'A'  THEN 4.0
                  WHEN 'A-' THEN 3.7
                  WHEN 'B+' THEN 3.3
                  WHEN 'B'  THEN 3.0
                  WHEN 'B-' THEN 2.7
                  WHEN 'C+' THEN 2.3
                  WHEN 'C'  THEN 2.0
                  WHEN 'D'  THEN 1.0
                  ELSE 0.0
                END >= CASE COALESCE(p.nilai_minimal, 'C')
                  WHEN 'A'  THEN 4.0
                  WHEN 'A-' THEN 3.7
                  WHEN 'B+' THEN 3.3
                  WHEN 'B'  THEN 3.0
                  WHEN 'B-' THEN 2.7
                  WHEN 'C+' THEN 2.3
                  WHEN 'C'  THEN 2.0
                  WHEN 'D'  THEN 1.0
                  ELSE 0.0
                END
      )
    ORDER BY p.prasyarat_kode_mk
    """
)


def get_unmet_prerequisites(
    db: Session,
    nim: str,
    kode_mk: str,
    semester_sekarang: int,
) -> list[UnmetPrerequisite]:
    """Mengambil seluruh prasyarat mata kuliah `kode_mk` yang belum lulus
    (nilai >= nilai_minimal, default C) oleh mahasiswa `nim` di semester sebelumnya.
    """
    rows = db.execute(
        UNMET_PREREQUISITES_SQL,
        {
            "nim": nim,
            "kode_mk": kode_mk,
            "semester_sekarang": semester_sekarang,
        },
    ).mappings()

    return [
        UnmetPrerequisite(
            kode_mk=row["kode_mk"],
            nama=row["nama"],
            nilai_minimal=row["nilai_minimal"],
        )
        for row in rows
    ]
