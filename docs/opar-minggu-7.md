# Catatan OPAR — Minggu 7 (Modul Jadwal & Ruangan)

Framework **OPAR** (*Observe – Plan – Act – Reflect*) untuk mendokumentasikan analisis masalah rekayasa dan verifikasi keputusan desain pada Minggu 7.

---

## Siklus OPAR 1: Konkurensi Dua Admin pada Satu Ruangan/Dosen & Optimasi Interval Tree

### 1. Observe (Observasi)
- Meskipun logika `_bentrok_di_db()` sudah benar dalam eksekusi tunggal, saat **dua admin bekerja bersamaan** (dua terminal/request paralel) untuk memasukkan *Basis Data A* dan *Statistika B* ke ruang `A101` Senin pukul `08:00`:
  1. Transaksi Admin 1 menjalankan query bentrok → kosong.
  2. Sebelum Admin 1 `commit`, transaksi Admin 2 menjalankan query bentrok → juga melihat kosong.
  3. Keduanya melakukan `commit` → **jadwal bentrok lolos ke database**.
- Selain itu, spesifikasi tugas meminta optimasi dengan *Interval Tree*, namun pada skala kampus (~600 jadwal per semester) rata-rata hanya terdapat 6–8 jadwal per ruangan per hari.

### 2. Plan (Rencana)
1. Terapkan **pessimistic row locking** (`SELECT ... FOR UPDATE` / `with_for_update()`) pada baris `Ruangan` dan `Dosen` di awal transaksi `_simpan()` sebelum menjalankan `_bentrok_di_db()`.
2. Tetapkan **urutan penguncian yang konsisten** (selalu kunci `Ruangan` terlebih dahulu, baru `Dosen`) agar dua transaksi tidak saling menunggu selamanya (*deadlock*).
3. Tambahkan `self.db.add(jadwal)` di akhir transaksi tepat sebelum `commit()` agar mekanisme *autoflush* SQLAlchemy tidak mengganggu query pengecekan bentrok.
4. Lakukan benchmark empiris `detect_naive` vs `detect_schedule_conflict` (grouping + sort & sweep) sebelum memutuskan apakah *Interval Tree* perlu dipasang, lalu tuangkan hasilnya di ADR.

### 3. Act (Tindakan)
- Mengimplementasikan `SchedulingService._kunci()` dengan urutan lock deterministik (`Ruangan` → `Dosen`) menggunakan `.with_for_update()` di `app/services/scheduling.py`.
- Mengimplementasikan pengecualian diri sendiri (`Jadwal.id != abaikan_id`) pada `_bentrok_di_db()` agar operasi `PUT` (mis. menggeser kuliah 15 menit) tidak dianggap bentrok dengan dirinya sendiri.
- Menyusun test lengkap:
  - Example-based test (`tests/test_conflict.py`) & API test (`tests/test_scheduling_api.py`).
  - Property-based & differential test (`tests/test_conflict_property.py`) menggunakan Hypothesis (500 contoh/properti).
- Menjalankan benchmark empiris (`scripts/benchmark_conflict.py`) dari `N = 40` hingga `N = 5,000` jadwal dan menyusun `docs/adr/001-tunda-interval-tree.md`.

### 4. Reflect (Refleksi)
- **Limitasi SQLite vs MySQL**: SQLite mengabaikan klausa `FOR UPDATE` (menggunakan table/file-level locking, bukan row-level locking seperti InnoDB). Oleh karena itu, pembuktian skenario konkurensi dua admin **harus dijalankan di MySQL (InnoDB)** (bukan hanya di suite pytest SQLite in-memory). Sebagai catatan arsitektur, PostgreSQL menyediakan `EXCLUDE USING gist (... WITH &&)` untuk menolak irisan rentang langsung di level DB, sedangkan MySQL tidak memilikinya sehingga *row lock* menjadi pendekatan paling tepat.
- **Keputusan Interval Tree**: Benchmark nyata membuktikan bahwa pada `N = 600` jadwal, *Grouping + Sort & Sweep* selesai dalam **1.04 ms** tanpa pustaka eksternal. Menunda Interval Tree dan mendokumentasikannya di ADR adalah keputusan rekayasa yang jujur, terukur, dan menghindari *premature optimization*.
- **Limitasi yang dicatat untuk Minggu 8**:
  - Pencarian bentrok saat ini belum memfilter berdasarkan `kelas.semester` aktif (diasumsikan 1 semester aktif di tabel jadwal); perlu ditambahkan join/filter semester jika data multi-semester disimpan bersamaan.
  - Generator jam pada Hypothesis memakai jam bulat (`time(jam, 0)`), sehingga kasus batas menit (`09:40`) tetap wajib dijaga oleh example-based test.
