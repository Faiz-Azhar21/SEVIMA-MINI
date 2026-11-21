# SEVIMA-Mini — Modul Jadwal & Ruangan (Materi 4: Minggu 7–8)

Implementasi lengkap **Modul Jadwal & Ruangan** untuk mata kuliah Pemrograman Berorientasi Objek (PBO), mencakup fondasi Minggu 7 dan seluruh deliverable Minggu 8.

## Fitur Utama & Pemetaan Deliverable

1. **Scheduling Service (35%)** — `app/scheduling/conflict.py`, `app/scheduling/service.py`
   - CRUD jadwal atomik dengan row locking (`with_for_update`) dan HTTP `409 Conflict`.
   - Deteksi bentrok 3 dimensi (`room_conflict`, `lecturer_conflict`, `time_overlap`) memakai interval setengah terbuka `[mulai, selesai)` dan **AVL-balanced Augmented Interval Tree**.
   - Capacity check: `max(kelas.kuota, enrolled) <= ruangan.kapasitas`.
2. **Observer Pattern + Transactional Outbox (25%)** — `app/scheduling/observer.py`, `app/scheduling/outbox.py`
   - `ScheduleSubject` (alias `NotificationManager`), `ScheduleEvent` (`frozen=True`), `Observer` & `Channel` berbasis `Protocol`.
   - 3 observer: `StudentObserver`, `LecturerObserver` (termasuk dosen lama saat diganti), `AdminObserver`.
   - 3 kanal simulasi log: `EMAIL`, `SMS`, `PUSH` (`LogChannel`) dengan **Idempotency Key** (`{event_id}:{penerima}:{channel}`).
   - `Outbox` ditulis dalam 1 transaksi bersama update/delete jadwal + invalidasi KRS; `OutboxDispatcher` mengirim **setelah `commit`** (`skip_locked=True`, `MAX_ATTEMPTS=5`, isolasi `try/except` per observer).
3. **Conflict Resolver UI & AI Rescheduling (20%)** — `app/scheduling/ai_rescheduler.py`, `app/scheduling/router.py`, `app/static/index.html`
   - Slot tersedia dihitung secara deterministik oleh kode sendiri.
   - Interface `LLMClient(Protocol)` (mendukung `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, dan fallback lokal offline).
   - **4 Saringan Validasi (`saring_saran`)**: parsing JSON, Pydantic `Saran`, eksistensi & kapasitas ruangan di DB, serta simulasi `detect_schedule_conflict`.
   - Dashboard Admin HTML + RBAC (`X-Role: admin_akademik`) + tombol **Terapkan** lewat satu pintu `SchedulingService.update()`.
4. **Integrasi KRS (15%)** — `app/krs/models.py`, `app/krs/invalidator.py`
   - Penambahan `Actor.SISTEM` dan 2 transisi resmi ke `REVISION` (total matriks `4 × 4 × 3 = 48` kombinasi: 6 sah, 42 ilegal).
   - `KRSInvalidator` hanya mengubah status `SUBMITTED` dan `APPROVED` (membiarkan `DRAFT`/`REVISION`), tanpa `commit()` sendiri.
5. **Calendar `.ics`, Testing, & Dokumentasi (5%)** — `app/scheduling/ical.py`, `tests/`, `docs/`
   - Ekspor RFC 5545 `GET /api/mahasiswa/{nim}/jadwal.ics` (`CRLF`, `TZID=Asia/Jakarta`, `UNTIL` UTC, `UID` stabil, `SEQUENCE` inkremental).
   - UML Sequence & Class Diagram Mermaid: `docs/sequence_observer.md`.
   - AI Log OPAR: `docs/ai_log_opar.md`, PR template: `docs/pr_template.md`, panduan Viva: `docs/viva_prep.md`.

## Cara Menjalankan

### 1. Jalankan Pengujian Otomatis (`pytest`)
```bash
pytest -v
```

### 2. Jalankan Demo Singkat (CLI)
```bash
python demo.py
```

### 3. Jalankan Server FastAPI & Buka Dashboard Conflict Resolver
```bash
uvicorn app.main:app --reload
```
Lalu buka `http://127.0.0.1:8000/` (UI) atau `http://127.0.0.1:8000/docs` (Swagger UI — gunakan header `X-Role: admin_akademik` pada endpoint `/api/jadwal/*`).
