# SEVIMA-Mini — Modul KRS (Kartu Rencana Studi) | Minggu 5–6

Implementasi lengkap tugas **Pemrograman Berorientasi Objek (Materi 3: Minggu 5–6)** berupa sistem pengisian dan persetujuan KRS dengan validasi aturan bisnis kompleks, State Machine, Transaction Management (ACID), Concurrency Control, Property-Based Testing, dan Challenge Opsional **KRS Recommendation AI**.

---

## Pemetaan Deliverables & Kriteria Sukses

| # | Deliverable (Bobot) | Lokasi File | Ringkasan Implementasi |
| :-: | :--- | :--- | :--- |
| 1 | **Database Schema (20%)** | `sql/schema.sql`, `app/models.py`, `app/queries.py` | Tabel `matakuliah`, `krs`, `krs_detail`, `prerequisite` + `riwayat_nilai`, `log_krs`, `notifikasi`, composite indexes, dan SQL query cek prasyarat (`NOT EXISTS`). |
| 2 | **KRS Manager Service (40%)** | `app/service.py`, `app/state_machine.py`, `app/main.py` | `add_course`, `remove_course`, `validate_krs`, `submit_krs`, `approve_krs`, `revise_krs`, State Machine 4 state, Otorisasi 2 lapis, Transaksi ACID, Pessimistic + Optimistic Locking, dan API FastAPI. |
| 3 | **Validation Rules (25%)** | `app/validators.py`, `app/exceptions.py` | Chain of Responsibility: `SKSValidator` (≤ 24), `PrerequisiteValidator` (nilai ≥ C semester lalu), `ConflictValidator` (hari + jam overlap), `DuplicateValidator` (anti double enrollment). |
| 4 | **Unit + Integration Tests (10%)** | `tests/` | Unit validator, Exhaustive State Machine (32 kombinasi: 4 sah + 28 ilegal), Integration service + rollback ACID + stale version, API `TestClient` (200/400/403/409/422), dan Hypothesis Property-Based Testing (2 × 1000 kombinasi). |
| 5 | **AI Log + OPAR (5%)** | `prompts/ai-usage-log.md`, `docs/ADR-001-state-machine.md`, `docs/PR_TEMPLATE.md` | Catatan prompt, revisi manual, refleksi OPAR, ADR keputusan State Machine, PR template jujur soal limitasi, serta panduan Viva (`docs/VIVA_GUIDE.md`). |
| + | **Challenge Opsional (+10%)** | `app/recommender.py`, `tests/test_recommender.py` | **KRS Recommendation AI**: CSP Backtracking Solver (prioritas `WAJIB > PILIHAN`, kelas paralel bebas bentrok, SKS ideal ≤ 24) + Function-Calling LLM Agent dengan guardrail `validate_krs()`. |

---

## Checklist Kriteria Sukses
- [x] Mahasiswa bisa tambah/hapus MK via API (`POST /api/krs/{nim}/courses`, `DELETE /api/krs/{nim}/courses/{kode_mk}`)
- [x] Validasi prasyarat berjalan otomatis (SQL `NOT EXISTS` dengan nilai ≥ C semester sebelumnya)
- [x] Error message jelas (contoh: `"Prasyarat tidak terpenuhi: Kalkulus I"`, `"Transisi tidak diizinkan: DRAFT ke APPROVED"`)
- [x] State transition tidak bisa diskip (terbukti lewat 28 test kombinasi ilegal)
- [x] Test lulus dengan berbagai edge case & 1000 kombinasi acak Hypothesis

---

## Cara Menjalankan

### 1. Instalasi Dependensi
```bash
pip install -r requirements.txt
```

### 2. Menjalankan Seluruh Pengujian & Coverage
```bash
pytest -v --cov=app --cov-report=term-missing
```

### 3. Menjalankan Server API FastAPI
```bash
uvicorn app.main:app --reload
```
Dokumentasi interaktif Swagger UI tersedia di `http://127.0.0.1:8000/docs`.

---

## Daftar Endpoint API

| Method | Endpoint | Body | Status Codes |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/krs/{nim}` | — | `200`, `404` |
| `POST` | `/api/krs/{nim}/courses` | `{"kode_mk": "..."}` | `201`, `400`, `404`, `409` |
| `DELETE` | `/api/krs/{nim}/courses/{kode_mk}` | — | `200`, `404`, `409` |
| `GET` | `/api/krs/{nim}/validate` | — | `200`, `404` |
| `POST` | `/api/krs/{nim}/submit` | — | `200`, `400`, `409` |
| `POST` | `/api/krs/{nim}/approve` | `{"dosen_pa_id": 101, "version": 2}` | `200`, `403`, `409` |
| `POST` | `/api/krs/{nim}/revise` | `{"dosen_pa_id": 101, "catatan": "..."}` | `200`, `403`, `409`, `422` |
| `POST` | `/api/krs/{nim}/recommend` | `{"desired_courses": [...], "max_sks": 24, "target_sks": 20}` | `200`, `404` |
