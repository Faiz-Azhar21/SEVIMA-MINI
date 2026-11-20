"""Query SQL prasyarat mata kuliah menggunakan pola NOT EXISTS + skala_nilai.

Menghindari jebakan perbandingan string `nilai >= 'C'` (karena secara ASCII
'D' > 'C' dan 'B' < 'C', sehingga hasilnya terbalik total).
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

MIN_BOBOT_LULUS = 2.00  # Setara nilai huruf 'C' pada skala_nilai

PRASYARAT_BELUM_LULUS_SQL = text(
    """
    SELECT mk.kode_mk, mk.nama
    FROM prerequisite p
    JOIN matakuliah mk ON mk.kode_mk = p.kode_prasyarat
    WHERE p.kode_mk = :kode_mk
      AND NOT EXISTS (
          SELECT 1
          FROM krs k
          JOIN krs_detail d ON d.krs_id = k.id
          JOIN skala_nilai s ON s.huruf = d.nilai
          WHERE k.nim = :nim
            AND k.semester < :semester
            AND d.kode_mk = p.kode_prasyarat
            AND s.bobot >= :min_bobot
      )
    ORDER BY mk.kode_mk
    """
)


def prasyarat_belum_lulus(
    db: Session,
    nim: str,
    kode_mk: str,
    semester: str,
    min_bobot: float = MIN_BOBOT_LULUS,
) -> list[str]:
    """Kembalikan daftar nama mata kuliah prasyarat yang belum lulus (nilai < C)
    pada semester sebelumnya (< `semester`).
    """
    rows = db.execute(
        PRASYARAT_BELUM_LULUS_SQL,
        {
            "nim": nim,
            "kode_mk": kode_mk,
            "semester": semester,
            "min_bobot": min_bobot,
        },
    ).all()
    return [row.nama for row in rows]
