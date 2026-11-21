# SEVIMA-Mini — Materi 5 Minggu 9: Modul Nilai, GPA Calculator, & Audit Trail

Implementasi **Materi 5 – Minggu 9 (Bagian 1 dari Modul Nilai & Transkrip)** untuk mata kuliah Pemrograman Berorientasi Objek (PBO).

## Fitur Utama Minggu 9

1. **Grade Management & Guards (`GradeService`)**:
   - Satu grade = satu baris `krs_detail` dengan Foreign Key `krs_detail.nilai → skala_nilai.huruf`.
   - Otorisasi 2 lapis (peran + kepemilikan): hanya **dosen pengampu kelas** (`is_pengampu` via tabel `jadwal`) yang boleh mengisi nilai (`403` untuk dosen lain).
   - Validasi presensi minimal **75%** (tepat `75%` masih diperbolehkan) melalui `PresensiPort` + `PresensiStub` (*Dependency Inversion Principle* hingga modul Presensi Minggu 12).
   - *Row locking* (`SELECT ... FOR UPDATE`), idempotensi jika nilai sama, dan **alasan wajib** saat mengubah nilai yang sudah ada.
   - Endpoint `PUT /api/kelas/{kelas_id}/nilai/{nim}` + form web sederhana di `GET /`.
2. **GPA Calculator (`hitung_ips`, `hitung_ipk`, `GPACalculator`)**:
   - Fungsi murni tanpa DB di `app/domain/gpa.py` memakai `Decimal` + `ROUND_HALF_UP` (menghindari *bug* `float` dan *banker's rounding* `3.125 → 3.12`).
   - **IPS**: menghitung seluruh MK pada semester target, termasuk nilai `E`.
   - **IPK**: deduplikasi per `kode_mk` (ambil bobot tertinggi, bukan `max` huruf string), baru saring MK dengan `skala_nilai.lulus == True`. Mahasiswa baru tanpa nilai mengembalikan `Decimal("0.00")`.
   - Strategi **compute-on-read** (`GET /api/mahasiswa/{nim}/ipk` mengembalikan string `"3.08"` agar tidak dikonversi jadi `float` di klien).
   - Dilengkapi versi SQL CTE + Window Function (`ROW_NUMBER()`) di `NilaiRepo.calculate_ipk_sql()` untuk *differential testing*.
3. **Audit Trail (`grade_history` & View `v_riwayat_nilai`)**:
   - Setiap input perdana (`old_value=None`) maupun perubahan nilai dicatat ke `grade_history` (*append-only*, timestamp UTC) dalam **satu transaksi atomik** dengan update nilai.
   - SQL View `v_riwayat_nilai` tersedia untuk kueri riwayat per `nim` (`GET /api/mahasiswa/{nim}/riwayat-nilai`).
4. **Testing & Dokumentasi Engineering**:
   - `tests/test_gpa.py`: 12 kasus `parametrize` IPK + 4 kasus IPS + uji tukar skala (`D` lulus) + 3 properti `hypothesis`.
   - `tests/test_grade_service.py`, `tests/test_repository_and_sql.py`, `tests/test_api.py`, `tests/test_migration.py`.
   - `docs/pertanyaan-stakeholder-m9.md`, `docs/ADR-005-modul-nilai-dan-ipk.md`, `prompts/ai-usage-log.md` (OPAR), dan `.github/PULL_REQUEST_TEMPLATE.md`.

## Cara Menjalankan

### 1. Jalankan Pengujian (Unit, Property-Based, Integration, API, Migrasi)
```bash
pytest --cov=app --cov-report=term-missing
```

### 2. Jalankan Migrasi Alembic (Opsional untuk DB lokal)
```bash
alembic upgrade head
```

### 3. Jalankan Aplikasi Web & API
```bash
uvicorn app.main:app --reload
```
- Form Input Nilai Dosen: `http://127.0.0.1:8000/`
- Dokumentasi API (Swagger): `http://127.0.0.1:8000/docs`
