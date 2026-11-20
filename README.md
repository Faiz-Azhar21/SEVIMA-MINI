# SEVIMA-Mini — Modul KRS (Materi 3 · Minggu 5)

Implementasi fondasi **Modul KRS (Kartu Rencana Studi)** melanjutkan Modul PMB (Minggu 3–4) dengan stack **FastAPI + SQLAlchemy 2.0 + Pydantic v2 + Alembic + Pytest**.

## Struktur Proyek

```text
├── alembic/
│   ├── env.py
│   └── versions/
│       └── 0001_initial_pmb_krs_schema.py   # Migrasi 4 tabel KRS + skala_nilai + calon_mahasiswa
├── app/
│   ├── api/krs.py                           # Router FastAPI tipis (request -> service -> HTTP)
│   ├── models/
│   │   ├── base.py                          # Declarative Base
│   │   ├── pmb.py                           # CalonMahasiswa (induk FK nim)
│   │   └── krs.py                           # MataKuliah, prerequisite, SkalaNilai, KRS, KRSDetail, KRSStatus
│   ├── queries/prerequisite.py              # Query SQL NOT EXISTS + skala_nilai
│   ├── schemas/krs.py                       # Pydantic v2 schemas
│   ├── services/krs_manager.py              # KRSManager (add_course, remove_course, validate_krs + row lock)
│   ├── validators/
│   │   ├── base.py                          # ValidationResult, KRSContext, Validator(ABC), build_chain
│   │   └── krs.py                           # Duplicate, SKS, Prerequisite, Conflict Validator
│   ├── database.py                          # Engine & session (SQLite FK ON + kompatibel MySQL)
│   └── main.py                              # Entry point FastAPI
├── docs/
│   ├── adr/ADR-001-krs-validation-design.md # ADR: fail-fast vs collect-all, urutan chain, jadwal bersambung
│   ├── AI_USAGE_LOG.md                      # Jejak prompt, review 6 jebakan AI, revisi, dan catatan viva
│   └── EXPLAIN_PROOF.md                     # Bukti EXPLAIN sebelum vs sesudah optimasi index
├── scripts/
│   ├── seed.py                              # Seed data dummy (idempotent)
│   └── explain_proof.py                     # Generator bukti EXPLAIN & benchmark 10.000 baris
└── tests/                                   # Unit & integration tests (pytest + coverage)
```

## Cara Menjalankan

### 1. Jalankan Migrasi Database (Alembic)
Default menggunakan SQLite lokal (`sqlite:///./sevima_mini.db`):
```powershell
alembic upgrade head
```

### 2. Isi Data Dummy (*Seeding*)
```powershell
python scripts/seed.py
```

### 3. Jalankan Pengujian & Coverage
```powershell
pytest --cov=app --cov-report=term-missing
```

### 4. Generate Ulang Bukti `EXPLAIN` Optimasi Index
```powershell
python scripts/explain_proof.py
```
Hasil bukti tersimpan di `docs/EXPLAIN_PROOF.md`.

### 5. Jalankan Server FastAPI
```powershell
uvicorn app.main:app --reload
```
Buka dokumentasi interaktif Swagger UI di `http://127.0.0.1:8000/docs`.

**Contoh Endpoint:**
- `GET /api/krs/202401001?semester=20251` — Lihat KRS Budi
- `POST /api/krs/202401001/courses?semester=20251` dengan body `{"kode_mk": "IF201"}` — Tambah MK
- `DELETE /api/krs/202401001/courses/IF201?semester=20251` — Hapus MK
- `GET /api/krs/202401001/validate?semester=20251` — Validasi menyeluruh (*collect-all*)

---

## Menjalankan pada MySQL (Pengujian Row Lock & `EXPLAIN`)

> **Catatan Penting**: SQLite mengabaikan klausa `SELECT ... FOR UPDATE`. Untuk menguji *row-level locking* pada skenario konkuren ("2 tab, 1 detik, 27 SKS") serta memverifikasi `EXPLAIN` MySQL (`type: ALL` vs `ref`/`eq_ref`), arahkan environment variable `DATABASE_URL` ke server MySQL Anda:

```powershell
pip install pymysql
$env:DATABASE_URL="mysql+pymysql://root:password@127.0.0.1:3306/sevima_mini"
alembic upgrade head
python scripts/seed.py
```

---

## Ruang Lingkup Minggu 5 vs Minggu 6
- **Selesai di Minggu 5**: Skema & migrasi Alembic, seed dummy, `KRSManager` (`add_course`, `remove_course`, `validate_krs`), 4 Validator Chain of Responsibility, Query `NOT EXISTS` + bukti `EXPLAIN`, endpoint FastAPI, test suite, ADR, dan AI Usage Log.
- **Disiapkan untuk Minggu 6**: State Machine (`KRSStatus` transitions), `submit_krs` & `approve_krs` (saat ini berupa *stub* `NotImplementedError`), *property-based testing* dengan `hypothesis`, OPAR, serta Challenge Opsional KRS Recommendation AI.
