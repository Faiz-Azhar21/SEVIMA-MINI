# Jejak Penggunaan AI — Minggu 9 (Modul Nilai & Transkrip, Bagian 1)

## Ringkasan Sesi

- **Minggu**: 9 (Materi 5, Bagian 1)
- **Fitur**: Input nilai (`GradeService` + `PUT /api/kelas/{id}/nilai/{nim}` + form web sederhana), `calculate_ips` & `calculate_ipk`, `PresensiPort`/`PresensiStub`, `grade_history` + view `v_riwayat_nilai`, migrasi Alembic, dan test suite.
- **Tujuan**: Nilai hanya masuk lewat pintu yang aman (dosen pengampu & presensi ≥ 75%), IPS/IPK tepat dengan `Decimal` + `ROUND_HALF_UP`, setiap perubahan meninggalkan jejak audit atomik.
- **AI / Tool**: AI Coding Assistant (VS Code / IDE)
- **Prompt Kunci**:
  - Meminta pemeriksaan ambiguitas & kontradiksi spesifikasi terlebih dahulu sebelum menulis kode:
    > *"Sebelum menulis kode, sebutkan semua ambiguitas atau kontradiksi di spesifikasi ini. Jangan memilih tafsiran sendiri."*
  - Meminta Python 3.12, memakai `Decimal` (BUKAN `float`) dengan `ROUND_HALF_UP` dua desimal dibulatkan sekali di akhir, fungsi murni tanpa DB (`hitung_ips`, `hitung_ipk`), definisi `lulus` dibaca dari `skala_nilai.lulus`, serta definisi eksplisit perbedaan IPS (termasuk `E`) dan IPK (nilai terbaik per `kode_mk`, hanya yang lulus).

---

## Revisi Manual & Perbandingan Terhadap Jebakan Kode AI Awal

| Area | Pola Bug Umum Kode AI Awal | Revisi / Implementasi Final |
| :--- | :--- | :--- |
| **Tipe & Pembulatan** | Memakai `float` dan `round()` Python (`3.125 → 3.12`) | Memakai `Decimal` (dari string/int) + `.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)` sekali di akhir (`3.125 → 3.13`), dan API mengirim IPK sebagai string JSON. |
| **Nilai Terbaik MK Diulang** | `max(rs, key=lambda r: r.huruf)` (`'E' > 'A'` memilih nilai terburuk!) | Bandingkan `skala[r.huruf].bobot` (numerik), bukan urutan alfabet huruf. |
| **SKS MK Diulang & Nilai E/D** | Menjumlahkan semua baris (SKS & mutu dobel, E ikut terhitung) | Deduplikasi per `kode_mk` (ambil bobot tertinggi) **dulu**, baru filter `skala[huruf].lulus`, sehingga SKS MK ulang hanya dihitung sekali. |
| **Edge Case Kosong & NULL** | `ZeroDivisionError` saat `total_sks == 0`; `KeyError: None` saat nilai belum terisi | `_rata()` mengembalikan `Decimal("0.00")` bila `total_sks == 0`; query `NilaiRepo` menyaring `KRSDetail.nilai.is_not(None)`. |
| **Gaya Query ORM** | `db.query(...)` (SQLAlchemy 1.x legacy) | Memakai `select(...)` gaya SQLAlchemy 2.0 + `with_for_update()` untuk *row locking*. |
| **Rumus IPK** | Menghitung IPK sebagai rata-rata IPS antar semester | Dihitung dari `Σ(bobot × SKS) / Σ(SKS)` seluruh MK lulus. |

---

## Siklus OPAR (Observe – Plan – Act – Reflect)

- **Observe**:
  - Dokumen spesifikasi mengandung kontradiksi `"Lulus MK jika nilai ≥ D (2.0)"` (karena `D = 1.0`, `C = 2.0`). AI yang tidak diingatkan cenderung memilih salah satu tafsiran diam-diam tanpa melapor.
  - Perhitungan dengan `float` + `round()` Python menghasilkan `3.12` untuk `25/8 = 3.125`, berbeda dari hitungan tangan aturan akademik `3.13`.
- **Plan**:
  - Buat pertanyaan tertulis formal ke stakeholder (`docs/pertanyaan-stakeholder-m9.md`) dan dokumentasikan asumsi sementara (minimal C) di `docs/ADR-005-modul-nilai-dan-ipk.md`.
  - Pindahkan status kelulusan ke data (`skala_nilai.lulus`), ganti semua perhitungan ke `Decimal` + `ROUND_HALF_UP`, dan pisahkan logika domain murni (`app/domain/gpa.py`) dari repository DB (`app/repositories/nilai_repo.py`).
  - Terapkan `PresensiPort` + `PresensiStub` agar tidak bergantung pada modul presensi Minggu 12.
- **Act**:
  - Implementasi migrasi Alembic (`0001_baseline_m5_m8` → `0002_m9_nilai_audit_trail`), `GradeService` (dengan `FOR UPDATE`, 2 penjaga, dan audit trail atomik), `NilaiRepo` + `GPACalculator` + SQL CTE differential test, router API + form web sederhana, serta test suite (`parametrize` 12 kasus IPK + 4 kasus IPS + 1 test tukar skala + 3 properti `hypothesis` + integration/API/migration tests).
- **Reflect**:
  - Spesifikasi pun bisa mengandung kesalahan/kontradiksi; tanggung jawab *engineer* adalah mengidentifikasi dan bertanya kepada stakeholder, bukan menebak diam-diam.
  - Memisahkan *functional core* (fungsi murni tanpa DB) membuat pengujian ratusan kasus otomatis via `hypothesis` berjalan cepat dan mampu menangkap mutasi bug seperti `max(huruf)` maupun pengambilan nilai terakhir.

---

## Kepatuhan AI-First Charter (Privasi Data)

- Nilai akademik adalah **data pribadi sensitif**.
- Selama penyusunan prompt, seed data, demo form web, dan seluruh test suite, **tidak ada satu pun data mahasiswa asli** yang digunakan atau ditempel ke prompt AI — seluruh contoh menggunakan data *dummy* fiktif (`Rina / 2025001`, `Budi / 2025002`, `Sari / 2025003`, `Dimas / 2025004`, `Tono / 2025099`).

---

## Uji & Hasil

- `tests/test_gpa.py`: 12 kasus IPK terparameterisasi + 4 kasus IPS + 1 uji tukar skala (`D` lulus) + 3 properti `hypothesis`.
- `tests/test_grade_service.py`: uji otorisasi `is_pengampu`, batas presensi `< 75%` vs tepat `75%`, wajib alasan saat edit, idempotensi, penolakan huruf asing di service & FK DB, serta query `v_riwayat_nilai`.
- `tests/test_repository_and_sql.py`: uji integrasi `NilaiRepo`/`GPACalculator` & *differential test* SQL CTE vs Python.
- `tests/test_api.py`: uji end-to-end endpoint FastAPI & form web HTML.
- `tests/test_migration.py`: uji Alembic `upgrade head` → `downgrade` → `upgrade head`.
