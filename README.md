# SEVIMA-Mini — Modul PMB (Penerimaan Mahasiswa Baru)

Implementasi tugas **Pemrograman Berorientasi Objek (Minggu 3–4)**: sistem pendaftaran calon mahasiswa baru dengan skema database tervalidasi, migrasi Alembic beserta rollback, state machine persetujuan (`pending` → `approved` / `rejected`), generator NIM otomatis yang idempotent serta aman dari *race condition*, dan pengujian otomatis dengan `pytest` (coverage **95.80%**).

---

## Fitur Utama

1. **Database Schema & Alembic Migration (dengan Rollback):**
   - 4 tabel: `program_studi`, `jalur_masuk` (`SNBP`, `SNBT`, `Mandiri`), `calon_mahasiswa`, dan `nim_counter`.
   - Constraint di level DB: `UNIQUE` email, `UNIQUE` NIM, `CheckConstraint` format email, format nomor telepon Indonesia (`08...`, `628...`, `+628...`), enum status (`pending`/`approved`/`rejected`), dan batas counter `0..9999`.
   - Dua revisi Alembic (`001_initial_pmb` & `002_nim_and_counter`) yang kompatibel dengan SQLite (`batch_alter_table`) maupun MySQL dan dapat di-rollback hingga `base`.
2. **REST API Endpoints (`/api/pmb`):**
   - `POST /api/pmb/register` — Mendaftarkan calon mahasiswa baru (`201 Created`, `400 Bad Request`, `409 Conflict`).
   - `GET /api/pmb/status/{calon_id}` — Cek status pendaftaran & NIM dengan `response_model=StatusOut` (memfilter data pribadi sensitif).
   - `PUT /api/pmb/approve/{calon_id}` — Menyetujui pendaftar (`pending` → `approved`), mencatat `approved_at` (UTC), dan generate NIM otomatis (`200 OK`, `400`, `404`, `409`).
   - `PUT /api/pmb/reject/{calon_id}` — Menolak pendaftar (`pending` → `rejected`, terminal state).
   - `GET /api/pmb/stats` — Dashboard statistik pendaftar (`total`, `per_status`, `per_prodi`, `per_jalur_masuk`) menggunakan agregasi SQL `GROUP BY` + `outerjoin`.
3. **Arsitektur OOP (`PMBService`):**
   - Seluruh aturan state machine, validasi bisnis, dan manajemen transaksi dienkapsulasi di `app/services/pmb_service.py`, bukan tersebar di lapisan router.
4. **NIM Generator Aman (`app/services/nim_generator.py`):**
   - Reset nomor urut otomatis per kombinasi `(tahun, kode_prodi)` dengan *zero-padding* 4 digit dan proteksi batas `> 9999`.
   - **Idempotent 2 lapis:** cek status `APPROVED` di logika + `UNIQUE` constraint di kolom `nim`.
   - **Anti Race Condition 3 lapis:** tabel `nim_counter` + `SELECT ... FOR UPDATE`, transaksi tunggal (`db.flush()` di generator, `db.commit()` di `PMBService.approve()`), dan retry otomatis (maks 3x) saat `IntegrityError`.

---

## Struktur Proyek

```text
sevima-mini-pmb/
├── alembic.ini
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       ├── 001_initial_pmb_schema.py      # Tabel dasar PMB + constraints + rollback
│       └── 002_add_nim_and_counter.py     # Kolom nim (UNIQUE) + tabel nim_counter + rollback
├── app/
│   ├── database.py                        # Engine, SessionLocal, Base, get_db DI
│   ├── models.py                          # SQLAlchemy 2.0 ORM Models & CheckConstraints
│   ├── schemas.py                         # Pydantic v2 input/output schemas & phone validator
│   ├── services/
│   │   ├── nim_generator.py               # format_nim(), format_nim_display(), generate_nim()
│   │   └── pmb_service.py                 # Class OOP PMBService (state machine & transaksi)
│   ├── routers/
│   │   └── pmb.py                         # FastAPI Router /api/pmb + dokumentasi Swagger
│   ├── seed.py                            # Seeder idempotent master prodi & jalur masuk
│   └── main.py                            # FastAPI app + custom 400 validation handler
├── tests/
│   ├── conftest.py                        # Fixture SQLite in-memory (StaticPool) + dependency_overrides
│   ├── test_nim_unit.py                   # Unit tests murni (format NIM, phone, counter bounds)
│   └── test_pmb_api.py                    # Integration tests (5 tes wajib + edge cases & guards)
├── prompts/
│   └── ai-usage-log.md                    # Dokumentasi penggunaan AI + OPAR
├── .github/
│   └── PULL_REQUEST_TEMPLATE.md           # Template Pull Request sesuai silabus
├── pyproject.toml
├── requirements.txt
└── README.md
```

---

## Keputusan Desain (ADR — Architecture Decision Records)

Karena terdapat beberapa ambiguitas pada dokumen spesifikasi tugas, keputusan berikut ditetapkan secara eksplisit dan dikunci dengan *automated test*:

### ADR-001: Format NIM 11 Digit Murni (`YYYYKKKXXXX`)
- **Konteks:** Dokumen tugas menulis format `[Tahun:4][Kode Prodi:3][Running Number:4]` (`YYYY[KODE]XXXX`, 11 digit) namun contohnya memakai strip (`2025001-0001`, 12 karakter).
- **Keputusan:** NIM disimpan dan dikembalikan oleh API dalam format **11 digit angka murni** tanpa strip (contoh: `20250010001`), karena konsisten dengan spesifikasi format, mudah divalidasi (`^\d{4}\d{3}\d{4}$`), dan mudah diurutkan. Helper presentasi `format_nim_display("20250010001") -> "2025001-0001"` disediakan jika UI/kartu mahasiswa memerlukan tanda strip.

### ADR-002: HTTP `400 Bad Request` untuk Error Validasi Input
- **Konteks:** Secara default FastAPI mengembalikan `422 Unprocessable Entity` ketika validasi Pydantic gagal, sedangkan spesifikasi Step 4 meminta `test_invalid_phone_format` mengembalikan `400`.
- **Keputusan:** Memasang custom `@app.exception_handler(RequestValidationError)` di `app/main.py` agar kegagalan validasi request mengembalikan **`400 Bad Request`** dengan detail error Pydantic yang tetap informatif.

### ADR-003: Kebijakan Approve Ulang (`approved` → `PUT /approve/{id}`)
- **Konteks:** Pendaftar yang sudah berstatus `approved` dapat menerima permintaan approve ulang akibat klik ganda admin atau *auto-retry* klien.
- **Keputusan:** Mengembalikan **`200 OK`** dengan **NIM lama** tanpa memanggil `generate_nim()` dan tanpa menaikkan counter `nim_counter` (sifat idempotent `PUT`). Sebaliknya, pendaftar berstatus `rejected` yang dicoba di-approve dikembalikan **`409 Conflict`**.

### ADR-004: Concurrency Database (MySQL InnoDB vs SQLite)
- **Konteks:** `threading.Lock()` di Python hanya berlaku dalam satu proses sehingga tidak aman untuk deployment multi-worker/multi-server.
- **Keputusan:** Menggunakan penguncian berbasis database (`SELECT ... FOR UPDATE` pada `nim_counter` dan `calon_mahasiswa`) dalam satu transaksi tunggal (`db.flush()` di generator, `db.commit()` di `PMBService`) + `UNIQUE` constraint + retry.
- **Limitasi:** Suite pengujian otomatis berjalan pada **SQLite in-memory** yang mengabaikan klausa `FOR UPDATE` (SQLite menggunakan database-level write lock). Pengujian konkurensi nyata pada **MySQL InnoDB** perlu dilakukan di lingkungan MySQL (atur env `DATABASE_URL=mysql+pymysql://user:pass@host/db`).

---

## Cara Menjalankan Proyek

### 1. Instalasi Dependensi
```bash
pip install -r requirements.txt
```

### 2. Migrasi Database & Uji Rollback (Alembic)
```bash
# Terapkan seluruh migrasi (Minggu 3 + Minggu 4)
alembic upgrade head

# Uji rollback 1 versi atau kembali ke awal
alembic downgrade -1
alembic downgrade base

# Naikkan kembali ke versi terbaru
alembic upgrade head
```

### 3. Seed Data Master (Program Studi & Jalur Masuk)
```bash
python -m app.seed
```

### 4. Jalankan Server & Buka Swagger UI
```bash
uvicorn app.main:app --reload
```
- **Swagger UI:** `http://127.0.0.1:8000/docs`
- **ReDoc:** `http://127.0.0.1:8000/redoc`
- **OpenAPI JSON:** `http://127.0.0.1:8000/openapi.json`

### 5. Jalankan Pengujian & Cek Coverage (Target ≥ 80%)
```bash
pytest -v --cov=app --cov-report=term-missing --cov-fail-under=80
```

**Hasil Verifikasi Terakhir:**
- **43 passed** dalam `2.87s`
- **Total Coverage:** `95.80%` (melampaui batas minimal `80%`)
- **Alembic Upgrade & Rollback:** `base → 001_initial_pmb → 002_nim_and_counter → 001_initial_pmb → base → head` lulus tanpa error.

---

## Ringkasan Persiapan Viva (Tanpa AI)

1. **Penanganan *race condition*:** 3 lapis — tabel `nim_counter` dengan `SELECT ... FOR UPDATE` agar transaksi paralel mengantre, satu transaksi atomik (`flush()` di `generate_nim`, `commit()` di `PMBService.approve()`), dan `UNIQUE` constraint pada `nim` + retry `IntegrityError`.
2. **Alasan kunci di database (bukan `threading.Lock()`):** `threading.Lock()` hanya mengunci thread di dalam 1 proses Python; pada server multi-worker (Uvicorn/Gunicorn) tiap worker memiliki lock sendiri. Database adalah satu-satunya *shared state* lintas worker.
3. **Kapan kunci dilepas:** Saat transaksi ditutup oleh `db.commit()` atau `db.rollback()`. Karena itu `generate_nim()` sengaja hanya memakai `db.flush()`.
4. **Jika transaksi gagal di tengah jalan:** Seluruh transaksi di-`rollback` otomatis sehingga `last_number` di `nim_counter` kembali ke angka semula, status pendaftar tetap `pending`, dan tidak terjadi nomor NIM yang bolong.
