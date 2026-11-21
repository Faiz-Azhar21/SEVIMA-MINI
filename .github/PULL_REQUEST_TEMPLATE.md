## Ringkasan Fitur (Minggu 9 — Modul Nilai & Transkrip, Bagian 1)

- [ ] Migrasi Alembic: `skala_nilai.bobot` (`Numeric(3, 2)`) & `skala_nilai.lulus`, FK `krs_detail.nilai → skala_nilai.huruf`, tabel `grade_history`, dan view `v_riwayat_nilai`.
- [ ] `GradeService` (satu pintu input/edit nilai, `FOR UPDATE`, validasi dosen pengampu + presensi ≥ 75% + wajib alasan saat edit, audit trail atomik).
- [ ] `PresensiPort` + `PresensiStub` (Dependency Inversion hingga Minggu 12) dan `is_pengampu`.
- [ ] Endpoint `PUT /api/kelas/{kelas_id}/nilai/{nim}`, `GET /api/mahasiswa/{nim}/ipk`, `GET /api/mahasiswa/{nim}/ips/{semester}`, `GET /api/mahasiswa/{nim}/riwayat-nilai`, serta form web sederhana (`GET /`).
- [ ] Fungsi murni `hitung_ips` & `hitung_ipk` (`Decimal` + `ROUND_HALF_UP`), `NilaiRepo`, `GPACalculator`, dan differential test SQL CTE vs Python.
- [ ] Test suite: 10+ kasus `parametrize` + 3 properti `hypothesis` + integration/API/migration tests.
- [ ] Dokumentasi: `docs/pertanyaan-stakeholder-m9.md`, `docs/ADR-005-modul-nilai-dan-ipk.md`, `prompts/ai-usage-log.md` (OPAR).

## Apa yang Dibantu AI & Prompt

- Lihat rincian lengkap, revisi manual, dan refleksi OPAR pada [`prompts/ai-usage-log.md`](prompts/ai-usage-log.md).
- Kepatuhan AI-First Charter: **hanya data dummy** yang digunakan dalam prompt, seed, dan test.

## Risiko Terbuka

1. **Presensi masih berupa `PresensiStub`**: Modul Presensi sesungguhnya baru dibangun di Minggu 12; adapter asli perlu di-wire ke `PresensiPort` saat Minggu 12 selesai.
2. **Batas kelulusan (`≥ D (2.0)`) belum dikonfirmasi stakeholder**: Saat ini memakai asumsi sementara minimal `C (2.00)`. Begitu stakeholder menjawab `docs/pertanyaan-stakeholder-m9.md`, perbarui baris `D` di tabel `skala_nilai`.
3. **Autentikasi dosen masih simulasi header (`X-Dosen-Id`)**: Akan terhubung dengan token/JWT sesi autentikasi penuh pada integrasi akhir.

## Cara Uji

```bash
# 1. Jalankan seluruh test suite (unit, property-based, integration, API, migration)
pytest --cov=app --cov-report=term-missing

# 2. (Opsional) Jalankan migrasi Alembic
alembic upgrade head

# 3. (Opsional) Jalankan server & buka form web dosen
uvicorn app.main:app --reload
# Akses http://127.0.0.1:8000/ untuk form web dan http://127.0.0.1:8000/docs untuk Swagger UI
```
