"""Pembuktian optimasi index menggunakan EXPLAIN QUERY PLAN (sebelum vs sesudah index).

Mensimulasikan beban malam terakhir KRS (~10.000 baris `krs_detail`) pada dua database
SQLite in-memory:
1. Tanpa index tambahan pada `krs` dan `krs_detail` (full table scan).
2. Dengan skema resmi (PK gabungan `prerequisite`, UNIQUE `krs(nim, semester)`,
   UNIQUE `krs_detail(krs_id, kode_mk)`, PK `skala_nilai`).

Menjalankan query `NOT EXISTS` prasyarat, mencatat rencana eksekusi (EXPLAIN QUERY PLAN)
serta perbandingan waktu rata-rata, dan menulis laporan bukti ke `docs/EXPLAIN_PROOF.md`.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_MD = ROOT_DIR / "docs" / "EXPLAIN_PROOF.md"

PREREQ_QUERY = """
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
        AND s.bobot >= 2.00
  )
ORDER BY mk.kode_mk
"""


def setup_db(with_indexes: bool, num_students: int = 500) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()

    if with_indexes:
        cur.executescript(
            """
            CREATE TABLE skala_nilai (
                huruf VARCHAR(2) PRIMARY KEY,
                bobot NUMERIC(3, 2) NOT NULL
            );
            CREATE TABLE matakuliah (
                kode_mk VARCHAR(10) PRIMARY KEY,
                nama VARCHAR(100) NOT NULL
            );
            CREATE TABLE prerequisite (
                kode_mk VARCHAR(10) NOT NULL,
                kode_prasyarat VARCHAR(10) NOT NULL,
                PRIMARY KEY (kode_mk, kode_prasyarat)
            );
            CREATE TABLE krs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nim VARCHAR(20) NOT NULL,
                semester VARCHAR(5) NOT NULL,
                UNIQUE (nim, semester)
            );
            CREATE TABLE krs_detail (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                krs_id INTEGER NOT NULL,
                kode_mk VARCHAR(10) NOT NULL,
                nilai VARCHAR(2),
                UNIQUE (krs_id, kode_mk)
            );
            """
        )
    else:
        # Simulasi skema AI mentah tanpa UNIQUE/composite index pada krs & krs_detail
        cur.executescript(
            """
            CREATE TABLE skala_nilai (
                huruf VARCHAR(2),
                bobot NUMERIC(3, 2)
            );
            CREATE TABLE matakuliah (
                kode_mk VARCHAR(10),
                nama VARCHAR(100)
            );
            CREATE TABLE prerequisite (
                kode_mk VARCHAR(10),
                kode_prasyarat VARCHAR(10)
            );
            CREATE TABLE krs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nim VARCHAR(20),
                semester VARCHAR(5)
            );
            CREATE TABLE krs_detail (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                krs_id INTEGER,
                kode_mk VARCHAR(10),
                nilai VARCHAR(2)
            );
            """
        )

    cur.executemany(
        "INSERT INTO skala_nilai (huruf, bobot) VALUES (?, ?)",
        [("A", 4.0), ("B", 3.0), ("C", 2.0), ("D", 1.0), ("E", 0.0)],
    )

    courses = [
        ("MA101", "Kalkulus I"),
        ("IF101", "Algoritma & Pemrograman"),
        ("IF201", "Struktur Data"),
        ("IF202", "Basis Data"),
        ("IF203", "Statistika"),
        ("IF207", "Kecerdasan Buatan"),
    ]
    cur.executemany("INSERT INTO matakuliah (kode_mk, nama) VALUES (?, ?)", courses)
    cur.executemany(
        "INSERT INTO prerequisite (kode_mk, kode_prasyarat) VALUES (?, ?)",
        [("IF201", "IF101"), ("IF202", "IF201"), ("IF207", "IF201"), ("IF207", "MA101")],
    )

    semesters = ["20231", "20232", "20241", "20242"]
    taken_courses = ["MA101", "IF101", "IF201", "IF202", "IF203"]
    grades = ["A", "B", "C", "B", "D"]

    krs_rows = []
    detail_rows = []
    krs_id = 1
    for i in range(1, num_students + 1):
        nim = f"20240{i:04d}"
        for sem in semesters:
            krs_rows.append((krs_id, nim, sem))
            for idx, mk in enumerate(taken_courses):
                nilai = "D" if (i == num_students and mk == "MA101") else grades[idx]
                detail_rows.append((krs_id, mk, nilai))
            krs_id += 1

    cur.executemany("INSERT INTO krs (id, nim, semester) VALUES (?, ?, ?)", krs_rows)
    cur.executemany(
        "INSERT INTO krs_detail (krs_id, kode_mk, nilai) VALUES (?, ?, ?)",
        detail_rows,
    )
    conn.commit()
    return conn


def run_explain_and_benchmark(conn: sqlite3.Connection, params: dict[str, str], runs: int = 50):
    cur = conn.cursor()
    plan_rows = cur.execute(f"EXPLAIN QUERY PLAN {PREREQ_QUERY}", params).fetchall()
    result_rows = cur.execute(PREREQ_QUERY, params).fetchall()

    start = time.perf_counter()
    for _ in range(runs):
        cur.execute(PREREQ_QUERY, params).fetchall()
    elapsed_ms = ((time.perf_counter() - start) / runs) * 1000.0
    return plan_rows, result_rows, elapsed_ms


def format_plan(plan_rows: list[tuple]) -> str:
    lines = ["id | parent | notused | detail", "---|--------|---------|-------"]
    for row in plan_rows:
        lines.append(f"{row[0]} | {row[1]} | {row[2]} | {row[3]}")
    return "\n".join(lines)


def main() -> None:
    num_students = 500
    total_details = num_students * 4 * 5  # 10.000 baris krs_detail
    params = {"nim": f"20240{num_students:04d}", "kode_mk": "IF207", "semester": "20251"}

    conn_before = setup_db(with_indexes=False, num_students=num_students)
    conn_after = setup_db(with_indexes=True, num_students=num_students)

    plan_before, res_before, ms_before = run_explain_and_benchmark(conn_before, params)
    plan_after, res_after, ms_after = run_explain_and_benchmark(conn_after, params)

    assert res_before == res_after == [("MA101", "Kalkulus I")], (res_before, res_after)
    speedup = ms_before / ms_after if ms_after > 0 else 0.0

    report = f"""# Bukti Optimasi Query Prasyarat (`EXPLAIN` Sebelum vs Sesudah Index)

Laporan ini dihasilkan otomatis oleh `scripts/explain_proof.py` menggunakan data dummy sebanyak **{num_students} mahasiswa × 4 semester × 5 mata kuliah = {total_details:,} baris `krs_detail`**.

## 1. Query Prasyarat (`NOT EXISTS` + `skala_nilai`)

```sql
{PREREQ_QUERY.strip()}
```

Parameter uji: `nim = '{params['nim']}'`, `kode_mk = '{params['kode_mk']}'` (*Kecerdasan Buatan*, prasyarat: `IF201` dan `MA101`), `semester = '{params['semester']}'`.
Hasil query pada kedua skema identik: **`{res_after}`** (karena mahasiswa lulus `IF201` dengan `C` tetapi mendapat `D` pada `MA101`).

---

## 2. Sebelum Optimasi Index (Tanpa PK/UNIQUE Index)

Seluruh tabel dipindai penuh (`SCAN`), terutama `krs_detail` ({total_details:,} baris) yang di-scan berulang di dalam subquery `NOT EXISTS`:

```text
{format_plan(plan_before)}
```

- **Waktu eksekusi rata-rata (50 iterasi)**: `{ms_before:.3f} ms`

---

## 3. Sesudah Optimasi Index (Skema Resmi SEVIMA-Mini)

Index utama terbentuk otomatis dari **Primary Key** dan **UNIQUE Constraint**:
- `prerequisite`: `PK (kode_mk, kode_prasyarat)`
- `krs`: `UNIQUE (nim, semester)` — urutan kolom: **equality (`nim =`) di depan, range (`semester <`) di belakang**
- `krs_detail`: `UNIQUE (krs_id, kode_mk)`
- `skala_nilai`: `PK (huruf)`

```text
{format_plan(plan_after)}
```

- **Waktu eksekusi rata-rata (50 iterasi)**: `{ms_after:.3f} ms`
- **Percepatan (*Speedup*)**: **`{speedup:.1f}x` lebih cepat** (semua `SCAN` berubah menjadi `SEARCH ... USING INDEX` / `USING COVERING INDEX`).

---

## 4. Referensi Verifikasi `EXPLAIN` pada MySQL

Saat dijalankan pada MySQL (setelah `alembic upgrade head`), jalankan:

```sql
EXPLAIN
SELECT mk.kode_mk, mk.nama
FROM prerequisite p
JOIN matakuliah mk ON mk.kode_mk = p.kode_prasyarat
WHERE p.kode_mk = 'IF207'
  AND NOT EXISTS (
      SELECT 1
      FROM krs k
      JOIN krs_detail d ON d.krs_id = k.id
      JOIN skala_nilai s ON s.huruf = d.nilai
      WHERE k.nim = '202401001'
        AND k.semester < '20251'
        AND d.kode_mk = p.kode_prasyarat
        AND s.bobot >= 2.00
  );
```

**Indikator yang diperiksa pada output `EXPLAIN` MySQL:**
- **Sebelum index**: kolom `type` bernilai `ALL` (*full table scan*), `key = NULL`, dan `rows` sebesar total baris tabel.
- **Sesudah index / constraint**: kolom `type` berubah menjadi `ref` / `eq_ref` / `range`, kolom `key` menampilkan `PRIMARY`, `uq_krs_nim_semester`, dan `uq_krs_detail_krs_mk`, serta `rows` turun drastis menjadi hanya beberapa baris.
- **Alternatif jika skema tanpa UNIQUE constraint**:
  ```sql
  CREATE INDEX ix_krs_nim_sem ON krs (nim, semester);
  CREATE INDEX ix_krs_detail_krs_mk ON krs_detail (krs_id, kode_mk);
  ```

## 5. Catatan Trade-off Index
Index mempercepat operasi baca (`SELECT`) secara drastis, tetapi menambah overhead pada operasi tulis (`INSERT`/`UPDATE`/`DELETE`) dan ruang penyimpanan karena B-Tree index harus ikut diperbarui. Oleh karena itu, index hanya dipasang pada kolom yang benar-benar digunakan pada klausa `WHERE`/`JOIN` query kritis — tidak di semua kolom.
"""

    OUTPUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_MD.write_text(report, encoding="utf-8")
    print(f"Bukti EXPLAIN tersimpan di: {OUTPUT_MD}")
    print(f"Tanpa index : {ms_before:.3f} ms/query")
    print(f"Dengan index: {ms_after:.3f} ms/query ({speedup:.1f}x lebih cepat)")


if __name__ == "__main__":
    main()
