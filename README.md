# SEVIMA-Mini — Modul Jadwal & Ruangan (Materi 4, Minggu 7)

Implementasi **Bagian 1 Modul Jadwal & Ruangan**: Constraint Satisfaction Problem (*hard constraints*), algoritma deteksi bentrok 3 dimensi (`waktu × ruangan × dosen`), `SchedulingService` dengan *capacity check* dan *pessimistic row lock*, REST API FastAPI, migrasi Alembic, seed data, pengujian (example-based + Hypothesis property/differential), serta dokumentasi jejak rekayasa (ADR, OPAR, AI Log, PR Template).

---

## Struktur Proyek

```text
sevima-mini/
├── alembic/
│   ├── env.py
│   └── versions/
│       ├── 001_baseline_krs.py           # Baseline Materi 3 (matakuliah lama, krs, krs_detail)
│       └── 002_modul_jadwal_ruangan.py   # Migrasi Minggu 7 (ruangan, dosen, kelas, jadwal, krs_detail.kelas_id)
├── app/
│   ├── database.py                       # Engine & Session SQLAlchemy 2.0 (SQLite default / MySQL via DATABASE_URL)
│   ├── main.py                           # FastAPI app + 1 global polymorphic ScheduleError handler
│   ├── models/
│   │   ├── krs.py                        # MataKuliah, KRS, KRSDetail (+kelas_id)
│   │   └── jadwal.py                     # Ruangan, Dosen, Kelas, Jadwal (CheckConstraints + 2 composite index)
│   ├── schemas/
│   │   └── jadwal.py                     # Pydantic v2 JadwalIn (time validator), JadwalOut, ConflictOut
│   ├── services/
│   │   ├── conflict.py                   # overlap(), detect_naive(), detect_schedule_conflict() (sort & sweep)
│   │   ├── exceptions.py                 # ScheduleError, NotFoundError(404), CapacityError(409), ScheduleConflictError(409)
│   │   └── scheduling.py                 # cek_kapasitas(), SchedulingService (CRUD + row lock + SQL conflict check)
│   └── routers/
│       └── jadwal.py                     # POST, PUT, DELETE, GET, GET /conflicts
├── scripts/
│   ├── seed.py                           # Seed >=10 ruangan, >=15 dosen, >=40 jadwal + 3 bentrok sengaja
│   └── benchmark_conflict.py             # Benchmark empiris naive vs sort & sweep (pendukung ADR)
├── tests/
│   ├── conftest.py                       # Fixture SQLite in-memory + FastAPI TestClient
│   ├── test_conflict.py                  # Example-based parametrize (5 bug klasik AI) + DB CheckConstraint
│   ├── test_conflict_property.py         # Hypothesis: invariant slot-counter & differential testing (sweep == naive)
│   └── test_scheduling_api.py            # Integration/API tests (201/200/204/404/409/422), seed, & migrasi Alembic
├── docs/
│   ├── adr/001-tunda-interval-tree.md    # ADR menunda Interval Tree dengan angka pengukuran nyata
│   └── opar-minggu-7.md                  # Catatan OPAR (konkurensi 2 admin, SQLite vs MySQL, ADR)
├── prompts/
│   └── ai-usage-log.md                   # Jejak prompt, revisi manual 5 bug klasik AI, dan hasil uji
├── .github/pull_request_template.md      # Template PR lengkap dengan bagian Risiko/Limitasi
├── alembic.ini
├── pyproject.toml
└── requirements.txt
```

---

## Cara Menjalankan

```bash
# 1. Jalankan migrasi database (default: SQLite lokal sevima_mini.db)
alembic upgrade head

# 2. Isi seed data (12 ruangan, 16 dosen, 45 kelas, 45 jadwal + bentrok sengaja)
python -m scripts.seed --reset

# 3. Jalankan pengujian lengkap beserta coverage
pytest --cov=app --cov-report=term-missing

# 4. Jalankan benchmark empiris detektor konflik
python -m scripts.benchmark_conflict

# 5. Jalankan server API lokal
uvicorn app.main:app --reload
```

### Pengujian dengan MySQL (untuk Pembuktian Row Lock Konkurensi)

SQLite tidak mengunci baris pada `SELECT ... FOR UPDATE`. Untuk membuktikan proteksi *race condition* ketika 2 admin menambah jadwal bersamaan, arahkan `DATABASE_URL` ke server MySQL (InnoDB):

```bash
# PowerShell
$env:DATABASE_URL = "mysql+pymysql://user:password@localhost:3306/sevima_mini"
alembic upgrade head
python -m scripts.seed --reset
uvicorn app.main:app
```

---

## Ringkasan Endpoint API

| Method | Endpoint | Status Sukses | Status Error | Keterangan |
| :--- | :--- | :---: | :---: | :--- |
| `GET` | `/api/jadwal` | `200` | — | Daftar seluruh jadwal kuliah |
| `POST` | `/api/jadwal` | `201` | `404`, `409`, `422` | Buat jadwal baru (validasi format, bentrok, kapasitas) |
| `PUT` | `/api/jadwal/{jadwal_id}` | `200` | `404`, `409`, `422` | Ubah jadwal (mengecualikan ID diri sendiri dari cek bentrok) |
| `DELETE` | `/api/jadwal/{jadwal_id}` | `204` | `404` | Hapus jadwal dalam 1 transaksi (hook Observer Minggu 8) |
| `GET` | `/api/jadwal/conflicts` | `200` | — | Daftar seluruh bentrok ruangan/dosen yang ada di DB (bahan dashboard Minggu 8) |
