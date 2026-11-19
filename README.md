# Sistem Modul PMB (Penerimaan Mahasiswa Baru) & NIM Generator Otomatis

Proyek implementasi modul backend Penerimaan Mahasiswa Baru (PMB) untuk sistem akademik perguruan tinggi berbasis **FastAPI**, **SQLAlchemy**, dan **Alembic** dengan generator NIM otomatis yang **thread-safe** dan **idempotent**.

---

## 📌 Fitur Utama

1. **Database Schema & Constraints**:
   - Tabel `program_studi` (id, kode 3 digit, nama, fakultas).
   - Tabel `jalur_masuk` (id, kode, nama, keterangan).
   - Tabel `calon_mahasiswa` (id, nama_lengkap, email, phone, tanggal_lahir, alamat, prodi_id, jalur_id, status, nim, created_at, approved_at).
   - **Database Constraints**: `unique email`, validasi nomor telepon format Indonesia (`+62`, `62`, `08`), dan status enum (`pending`, `approved`, `rejected`).
   - Skrip migrasi **Alembic** lengkap dengan fitur **rollback** (`upgrade` dan `downgrade`).

2. **RESTful API Endpoints**:
   - `POST /api/pmb/register`: Pendaftaran calon mahasiswa (status `pending`, status code 201).
   - `GET /api/pmb/status/{id}`: Cek status pendaftaran calon mahasiswa.
   - `PUT /api/pmb/approve/{id}`: Admin approval pendaftaran sekaligus auto-generate NIM unik.
   - `GET /api/pmb/stats`: Dashboard statistik jumlah pendaftar (total, per status, per program studi, per jalur masuk).
   - `GET /api/pmb/prodi` & `GET /api/pmb/jalur`: Master data program studi dan jalur seleksi.

3. **NIM Generator Otomatis (Thread-Safe & Idempotent)**:
   - Format: `[Tahun:4][Kode Prodi:3]-[Running Number:4]`
   - Contoh: `2025001-0001` (Teknik Informatika pendaftar pertama).
   - **Thread-Safe**: Menggunakan `threading.RLock` dan atomic query sequence untuk mencegah race conditions saat banyak request masuk secara bersamaan.
   - **Idempotent**: Pemanggilan approval berulang pada mahasiswa yang sudah disetujui tidak akan mengubah NIM yang telah diterbitkan.

4. **Web Portal UI & Swagger Documentation**:
   - Form pendaftaran interaktif dan dashboard admin langsung di browser via `http://localhost:8000/`.
   - Dokumentasi interaktif Swagger UI di `http://localhost:8000/docs` dan ReDoc di `http://localhost:8000/redoc`.

5. **Unit Testing & Code Coverage**:
   - 19 test case menggunakan `pytest` mencakup validasi input, duplikasi email, format telepon, konkurensi NIM, idempotency, dan migrasi database.
   - **Test Coverage: 94%** (melampaui target minimal 80%).

---

## 🛠️ Persyaratan Sistem

- Python 3.10+ (Direkomendasikan Python 3.12)
- Pip package manager

---

## 🚀 Cara Menjalankan Aplikasi

### 1. Instalasi Dependensi
```bash
pip install -r requirements.txt
```

### 2. Menjalankan Migrasi Database (Alembic)
Untuk menerapkan skema database:
```bash
python -m alembic upgrade head
```

Untuk menguji fitur rollback database:
```bash
python -m alembic downgrade base
python -m alembic upgrade head
```

### 3. Menjalankan Server API
Jalankan server menggunakan Uvicorn:
```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Buka di browser:
- **Web Portal PMB**: [http://localhost:8000/](http://localhost:8000/)
- **Swagger UI API Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc API Docs**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 🧪 Menjalankan Unit Tests & Coverage Report

Jalankan seluruh test suite dengan mengukur coverage:
```bash
python -m pytest --cov=app tests/ -v
```

Hasil coverage:
```text
Name                            Stmts   Miss  Cover
---------------------------------------------------
app\config.py                       7      0   100%
app\database.py                    12      4    67%
app\main.py                        52      7    87%
app\models\__init__.py              4      0   100%
app\models\calon_mahasiswa.py      34      1    97%
app\models\jalur_masuk.py          12      1    92%
app\models\program_studi.py        12      1    92%
app\routers\pmb.py                 34      0   100%
app\schemas\__init__.py             2      0   100%
app\schemas\pmb.py                 73      1    99%
app\services\nim_generator.py      21      3    86%
app\services\pmb_service.py        66      3    95%
---------------------------------------------------
TOTAL                             329     21    94%
```

---

## 📂 Struktur Direktori Proyek

```
TUGAS PEMOGRAMAN/
├── alembic/
│   ├── env.py                             # Konfigurasi runtime migrasi
│   ├── script.py.mako                     # Template generasi script migrasi
│   └── versions/
│       └── 001_initial_pmb_schema.py      # DDL skema PMB (upgrade & downgrade)
├── alembic.ini                            # Konfigurasi database Alembic
├── app/
│   ├── __init__.py
│   ├── config.py                          # Konfigurasi aplikasi & database
│   ├── database.py                        # Engine, declarative base, & get_db DI
│   ├── main.py                            # Entrypoint FastAPI, exception handlers, static mount
│   ├── models/                            # SQLAlchemy ORM Models
│   │   ├── __init__.py
│   │   ├── calon_mahasiswa.py             # Model tabel calon mahasiswa + constraints
│   │   ├── jalur_masuk.py                 # Model tabel master jalur masuk
│   │   └── program_studi.py               # Model tabel master program studi
│   ├── schemas/                           # Pydantic Schemas & Validators
│   │   ├── __init__.py
│   │   └── pmb.py                         # DTO untuk Request & Response PMB
│   ├── services/                          # Business Logic Services
│   │   ├── __init__.py
│   │   ├── nim_generator.py               # Algoritma Thread-Safe NIM Generator
│   │   └── pmb_service.py                 # Registrasi, Approval, dan Statistik
│   ├── routers/                           # API Route Handlers
│   │   ├── __init__.py
│   │   └── pmb.py                         # Endpoint /register, /status, /approve, /stats
│   └── static/
│       └── index.html                     # Portal Web UI interaktif pendaftaran & dashboard
├── tests/
│   ├── __init__.py
│   ├── conftest.py                        # Fixtures database in-memory & test client
│   ├── test_migrations.py                 # Pengujian migrasi upgrade & rollback
│   ├── test_nim_generator.py              # Pengujian format NIM, sequence, & konkurensi
│   └── test_pmb.py                        # Pengujian endpoints, error handling, idempotency
├── AI_USAGE_LOG.md                        # Log prompt & arsitektur AI
├── README.md                              # Dokumentasi lengkap proyek
└── requirements.txt                       # Daftar dependensi Python
```

---

## 📋 Contoh Payload API

### 1. Registrasi Mahasiswa Baru
- **Method**: `POST`
- **URL**: `/api/pmb/register`
- **Request Body**:
```json
{
  "nama_lengkap": "Dewi Sartika",
  "email": "dewi.sartika@example.com",
  "phone": "081234567890",
  "tanggal_lahir": "2005-04-12",
  "alamat": "Jl. Merdeka No. 45, Jakarta",
  "program_studi_id": 1,
  "jalur_masuk": "SNBP"
}
```
- **Response (201 Created)**:
```json
{
  "id": 1,
  "nama_lengkap": "Dewi Sartika",
  "email": "dewi.sartika@example.com",
  "phone": "081234567890",
  "tanggal_lahir": "2005-04-12",
  "alamat": "Jl. Merdeka No. 45, Jakarta",
  "program_studi_id": 1,
  "jalur_masuk": "SNBP",
  "status": "pending",
  "nim": null,
  "created_at": "2026-11-19T12:00:00",
  "approved_at": null,
  "program_studi": {
    "kode": "001",
    "nama": "Teknik Informatika",
    "fakultas": "Fakultas Ilmu Komputer",
    "id": 1
  }
}
```

### 2. Admin Approve & Auto Generate NIM
- **Method**: `PUT`
- **URL**: `/api/pmb/approve/1`
- **Response (200 OK)**:
```json
{
  "id": 1,
  "nama_lengkap": "Dewi Sartika",
  "status": "approved",
  "nim": "2026001-0001",
  "approved_at": "2026-11-19T12:05:00",
  "message": "Pendaftaran berhasil disetujui dan NIM berhasil digenerate."
}
```
