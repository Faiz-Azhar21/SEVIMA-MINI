# Bukti Optimasi Query Prasyarat (`EXPLAIN` Sebelum vs Sesudah Index)

Laporan ini dihasilkan otomatis oleh `scripts/explain_proof.py` menggunakan data dummy sebanyak **500 mahasiswa × 4 semester × 5 mata kuliah = 10,000 baris `krs_detail`**.

## 1. Query Prasyarat (`NOT EXISTS` + `skala_nilai`)

```sql
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
```

Parameter uji: `nim = '202400500'`, `kode_mk = 'IF207'` (*Kecerdasan Buatan*, prasyarat: `IF201` dan `MA101`), `semester = '20251'`.
Hasil query pada kedua skema identik: **`[('MA101', 'Kalkulus I')]`** (karena mahasiswa lulus `IF201` dengan `C` tetapi mendapat `D` pada `MA101`).

---

## 2. Sebelum Optimasi Index (Tanpa PK/UNIQUE Index)

Seluruh tabel dipindai penuh (`SCAN`), terutama `krs_detail` (10,000 baris) yang di-scan berulang di dalam subquery `NOT EXISTS`:

```text
id | parent | notused | detail
---|--------|---------|-------
4 | 0 | 216 | SCAN p
9 | 0 | 0 | CORRELATED SCALAR SUBQUERY 1
15 | 9 | 216 | SCAN d
20 | 9 | 45 | SEARCH k USING INTEGER PRIMARY KEY (rowid=?)
38 | 9 | 53 | SEARCH s USING AUTOMATIC PARTIAL COVERING INDEX (huruf=?)
60 | 0 | 53 | SEARCH mk USING AUTOMATIC COVERING INDEX (kode_mk=?)
71 | 0 | 0 | USE TEMP B-TREE FOR ORDER BY
```

- **Waktu eksekusi rata-rata (50 iterasi)**: `0.915 ms`

---

## 3. Sesudah Optimasi Index (Skema Resmi SEVIMA-Mini)

Index utama terbentuk otomatis dari **Primary Key** dan **UNIQUE Constraint**:
- `prerequisite`: `PK (kode_mk, kode_prasyarat)`
- `krs`: `UNIQUE (nim, semester)` — urutan kolom: **equality (`nim =`) di depan, range (`semester <`) di belakang**
- `krs_detail`: `UNIQUE (krs_id, kode_mk)`
- `skala_nilai`: `PK (huruf)`

```text
id | parent | notused | detail
---|--------|---------|-------
5 | 0 | 56 | SEARCH p USING COVERING INDEX sqlite_autoindex_prerequisite_1 (kode_mk=?)
12 | 0 | 0 | CORRELATED SCALAR SUBQUERY 1
20 | 12 | 48 | SEARCH k USING COVERING INDEX sqlite_autoindex_krs_1 (nim=? AND semester<?)
29 | 12 | 47 | SEARCH d USING INDEX sqlite_autoindex_krs_detail_1 (krs_id=? AND kode_mk=?)
35 | 12 | 47 | SEARCH s USING INDEX sqlite_autoindex_skala_nilai_1 (huruf=?)
48 | 0 | 46 | SEARCH mk USING INDEX sqlite_autoindex_matakuliah_1 (kode_mk=?)
58 | 0 | 0 | USE TEMP B-TREE FOR ORDER BY
```

- **Waktu eksekusi rata-rata (50 iterasi)**: `0.004 ms`
- **Percepatan (*Speedup*)**: **`206.1x` lebih cepat** (semua `SCAN` berubah menjadi `SEARCH ... USING INDEX` / `USING COVERING INDEX`).

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
