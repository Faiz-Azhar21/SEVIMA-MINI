# AI Usage Log — Modul PMB (SEVIMA-Mini)

Dokumen ini mencatat penggunaan AI secara transparan selama pengembangan Modul PMB (Minggu 3 dan Minggu 4) sesuai format silabus mata kuliah Pemrograman Berorientasi Objek, lengkap dengan revisi manual dan refleksi **OPAR** (*Observe – Plan – Act – Reflect*).

---

## Entri 1 — Minggu 3: Skema Database, Migration Alembic & Endpoint Registrasi

- **Minggu:** 3
- **Fitur:** Skema Database PMB (`program_studi`, `jalur_masuk`, `calon_mahasiswa`) + Alembic Migration + `POST /api/pmb/register`
- **Tujuan:** Menerjemahkan desain class diagram/UML menjadi model SQLAlchemy 2.0 beserta constraint database, migration script dengan rollback, dan endpoint pendaftaran calon mahasiswa dengan Dependency Injection.
- **LLM / Tool:** Mistral via HF Inference / Codeium / AI Coding Assistant
- **Prompt Kunci (3 Terbaik):**
  1. *"Desain skema database PMB dengan SQLAlchemy 2.0 (Mapped/mapped_column) untuk tabel `calon_mahasiswa`, `program_studi`, dan `jalur_masuk` (SNBP/SNBT/Mandiri). Tambahkan constraint unique email, format telepon Indonesia, dan enum status (`pending`/`approved`/`rejected`), lalu buat Alembic migration script lengkap dengan `downgrade()`."*
  2. *"Buat endpoint FastAPI `POST /api/pmb/register` dengan skema Pydantic v2, Dependency Injection `Depends(get_db)`, normalisasi email lowercase, dan respons HTTP `201 Created`, `400 Bad Request`, serta `409 Conflict` untuk email duplikat."*
  3. *"Tambahkan PRAGMA `foreign_keys=ON` otomatis untuk koneksi SQLite di SQLAlchemy engine agar constraint foreign key benar-benar ditegakkan saat pengembangan maupun pengujian."*
- **Kode AI Awal:** Lihat implementasi dasar pada `app/models.py`, `app/database.py`, `alembic/versions/001_initial_pmb_schema.py`, dan `app/routers/pmb.py` (tautkan ke commit awal saat repo di-push ke GitHub).
- **Revisi Manual:**
  - **Sinkronisasi inkonsistensi tabel vs enum `jalur_masuk`:** Prompt awal AI hanya membuat kolom enum tanpa tabel `jalur_masuk`. Direvisi manual dengan tetap membuat tabel master `jalur_masuk` (`kode` UNIQUE) yang direferensikan lewat Foreign Key dari `calon_mahasiswa.jalur_masuk` sekaligus `CheckConstraint`, sehingga memenuhi spesifikasi 3 tabel sekaligus memudahkan query `GROUP BY` di `/stats`.
  - **Constraint lintas-DBMS (SQLite & MySQL):** Mengubah regex SQL spesifik dialek menjadi `CheckConstraint` portabel (`LIKE '08%' OR LIKE '+628%' OR LIKE '628%'` + `length` 10–15) dan memadukannya dengan validator regex ketat di Pydantic (`validate_indonesian_phone`).
  - **Pemasangan `PRAGMA foreign_keys=ON`:** Ditambahkan melalui SQLAlchemy engine event listener di `app/database.py` karena SQLite secara default menonaktifkan enforcement foreign key.
- **Uji & Hasil:**
  - `alembic upgrade head` → `alembic downgrade base` → `alembic upgrade head` berhasil tanpa error.
  - Tes registrasi valid (`201`), duplikat email (`409`), format telepon/email invalid (`400`), dan database check constraint lulus seluruhnya.
- **OPAR:**
  - **Observe:** SQLite secara default tidak menegakkan `FOREIGN KEY` dan tidak mendukung operator `REGEXP` bawaan tanpa fungsi kustom.
  - **Plan:** Aktifkan `PRAGMA foreign_keys=ON` pada event `connect` engine, gunakan `CheckConstraint` SQL standar yang portabel, dan validasi ketat di lapisan Pydantic.
  - **Act:** Menerapkan event listener di `app/database.py`, constraint di `app/models.py` & migrasi `001_initial_pmb_schema.py`, serta validator di `app/schemas.py`.
  - **Reflect:** Memverifikasi constraint langsung di level DB (dengan tes bypass Pydantic) memastikan integritas data tetap terjaga meski ada input dari luar API.

---

## Entri 2 — Minggu 4: Alur Approve/Reject, NIM Generator Aman, Stats & Testing

- **Minggu:** 4
- **Fitur:** `PUT /api/pmb/approve/{id}`, `PUT /api/pmb/reject/{id}`, `GET /api/pmb/status/{id}`, `GET /api/pmb/stats`, `generate_nim()`, dan suite `pytest` + coverage ≥ 80%
- **Tujuan:** Menyelesaikan state machine PMB, menghasilkan NIM otomatis yang idempotent serta aman dari race condition, membangun dashboard statistik dengan `GROUP BY`, dan membuktikan kebenaran perilaku lewat automated testing.
- **LLM / Tool:** Mistral via HF Inference / Codeium / AI Coding Assistant
- **Prompt Kunci (3 Terbaik):**
  1. *"Buat `generate_nim(tahun, kode_prodi, db)` untuk FastAPI + SQLAlchemy 2.0 + MySQL InnoDB yang berjalan multi-worker. Gunakan tabel `nim_counter` dengan `SELECT ... FOR UPDATE`, kolom `nim` UNIQUE + retry pada `IntegrityError`, cek overflow > 9999, dan jangan panggil `db.commit()` di dalam fungsi (cukup `db.flush()`)."*
  2. *"Enkapsulasi seluruh aturan state machine PMB (`pending` → `approved`/`rejected`, terminal state guard, idempotent approve) ke dalam class OOP `PMBService`, lalu lengkapi endpoint `/status/{id}` dengan `response_model` terfilter dan `/stats` memakai `func.count()` + `GROUP BY` + `outerjoin`."*
  3. *"Buat fixture `pytest` di `tests/conftest.py` memakai SQLite in-memory (`StaticPool`, `check_same_thread=False`) dengan `app.dependency_overrides[get_db]`, mencakup 5 tes wajib Step 4, tes approve data invalid (`404`/`409`/`400`), tes counter tidak melompat saat approve 2x, dan simulasi retry `IntegrityError`."*
- **Kode AI Awal:** Lihat `app/services/nim_generator.py`, `app/services/pmb_service.py`, `alembic/versions/002_add_nim_and_counter.py`, dan `tests/` (tautkan ke commit/patch saat repo di-push ke GitHub).
- **Revisi Manual:**
  - **Mengganti `threading.Lock()` dengan database locking:** Solusi awal dari prompt generik *"thread-safe"* menghasilkan `threading.Lock()`, yang tidak efektif pada deployment multi-worker (Uvicorn/Gunicorn). Direvisi menggunakan tabel `nim_counter` + `.with_for_update()` (`SELECT ... FOR UPDATE`), `db.flush()` dalam transaksi tunggal milik `PMBService.approve()`, dan mekanisme retry (maks 3x) saat `IntegrityError`.
  - **Inisialisasi eksplisit `last_number=0`:** Baris baru `NimCounter` wajib mengisi `last_number=0` secara eksplisit sebelum `counter.last_number += 1`, karena default kolom SQLAlchemy baru berlaku saat `INSERT`.
  - **Migrasi `002_add_nim_and_counter.py` dengan `batch_alter_table`:** Agar penambahan/penghapusan kolom `nim` + constraint `UNIQUE` dapat di-upgrade dan di-rollback dengan bersih baik di SQLite maupun MySQL.
  - **Custom `RequestValidationError` handler (422 → 400):** FastAPI default mengembalikan `422` untuk validasi Pydantic yang gagal; ditambahkan handler eksplisit di `app/main.py` agar `test_invalid_phone_format` mengembalikan `400 Bad Request` sesuai spesifikasi Step 4, lalu dicatat pada ADR-002 di `README.md`.
  - **Penambahan `PUT /api/pmb/reject/{id}` & validasi kode prodi (`400`):** Ditambahkan agar enum `rejected` dapat dicapai via API dan seluruh kasus error approve (`404`, `400`, `409`) teruji penuh.
  - **Tes tajam idempotency:** Menambahkan asersi bahwa setelah pendaftar A di-approve 2x, pendaftar B berikutnya tetap menerima nomor `0002` (bukan `0003`).
- **Uji & Hasil:**
  - `pytest -v --cov=app --cov-report=term-missing --cov-fail-under=80` → **43 passed**, total coverage **95.80%** (target minimal 80%).
  - `alembic upgrade head` → `alembic downgrade -1` → `alembic downgrade base` → `alembic upgrade head` → **berhasil penuh**.
- **OPAR:**
  - **Observe:** Generator NIM naif (`read → modify → write` atau `threading.Lock()`) rentan menghasilkan NIM ganda saat 2 admin melakukan approve bersamaan di server multi-worker; selain itu, default FastAPI mengembalikan `422` alih-alih `400` pada error validasi input.
  - **Plan:** Pindahkan seluruh mekanisme penguncian ke database (`nim_counter` + `SELECT ... FOR UPDATE` + `UNIQUE` + retry) dalam satu transaksi atomik, pisahkan aturan state machine ke class `PMBService`, dan dokumentasikan keputusan desain (format NIM, 400 vs 422, idempotency 200) di `README.md`.
  - **Act:** Mengimplementasikan migrasi `002`, `nim_generator.py`, `pmb_service.py`, custom validation handler di `main.py`, serta 43 test case di `tests/`.
  - **Reflect:** Pengujian otomatis dengan SQLite in-memory sangat cepat (2,87 detik) dan mencapai coverage 95,80%, tetapi **tidak menguji perilaku row-level lock MySQL InnoDB** karena SQLite mengabaikan klausa `FOR UPDATE`. Oleh karena itu, limitasi ini dicatat secara jujur di PR template dan perlu diuji langsung di MySQL InnoDB sebelum masuk ke lingkungan produksi.
