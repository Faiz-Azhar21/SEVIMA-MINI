# Modul Presensi (QR Code) — Tugas Minggu 12

Sistem presensi perkuliahan berbasis **QR Code + JWT** yang di-generate dosen dan di-scan mahasiswa, dilengkapi validasi jadwal kuliah, enrollment, anti-replay token, geolocation (opsional), rate limiting, laporan presensi & export Excel (`.xlsx`), serta **AI Attendance Insights** untuk deteksi pola kehadiran dan *early warning*.

## Fitur & Pemetaan Deliverables

| Deliverable | Bobot | Implementasi |
| :--- | :---: | :--- |
| **1. QR Generation Service** | 30% | `app/services/qr_service.py` — generate QR PNG dari JWT `HS256` valid 15 menit dengan `jti` unik per sesi (rotasi otomatis mencegah *replay attack*). Endpoint: `GET /attendance/qr/{schedule_id}` & `GET /attendance/qr/{schedule_id}/info`. |
| **2. Attendance Recording** | 30% | `app/services/attendance_service.py` — `POST /attendance/scan` memvalidasi JWT & expiry, anti-replay `jti`, hari & window waktu jadwal, enrollment mahasiswa pada MK, lokasi Haversine (opsional), anti-duplikat scan, serta status `hadir` (≤ 15 menit) dan `terlambat` (15–30 menit). |
| **3. Attendance Report** | 20% | `app/services/report_service.py` — rekap persentase per mahasiswa (`GET /attendance/report/student/{nim}`), per MK dengan daftar *warning* `< 75%` (`GET /attendance/report/course/{course_id}`), dan export Excel 3 sheet (`GET /attendance/report/course/{course_id}/export`). |
| **4. AI Attendance Insights** | 15% | `app/services/ai_service.py` — deteksi pola hari/jam absen tinggi, *early warning* mahasiswa berisiko `< 75%`, dan rekomendasi tindakan dalam JSON terstruktur (`GET /attendance/ai/insights` & `POST /attendance/ai/analyze`). Mendukung pengayaan LLM opsional via `GEMINI_API_KEY` atau `OPENAI_API_KEY`. |
| **5. Security** | 5% | `app/security.py` — validasi expiration JWT + database session expiry, token `jti` anti-replay, sliding-window **rate limiting** (anti spam scan -> HTTP `429`), dan guard role dosen (`X-Role`). |

## Struktur Proyek

```text
Materi 12/
├── app/
│   ├── main.py                     # Entrypoint FastAPI, lifespan seeding, & dashboard UI
│   ├── config.py                   # Konfigurasi aplikasi & timezone (Asia/Jakarta)
│   ├── database.py                 # Koneksi SQLAlchemy (SQLite)
│   ├── models.py                   # ORM: Course, Student, Enrollment, Schedule, AttendanceSession, AttendanceRecord
│   ├── schemas.py                  # Skema Pydantic request/response
│   ├── security.py                 # JWT, anti-replay, Haversine geolocation, rate limiter, RBAC
│   ├── seed.py                     # Data seed realistis (3 MK, 10 mahasiswa, riwayat 6 sesi, jadwal live demo)
│   ├── routers/
│   │   └── attendance.py           # Endpoint REST API /attendance/*
│   ├── services/
│   │   ├── qr_service.py           # Deliverable 1: QR Generation
│   │   ├── attendance_service.py   # Deliverable 2: Scan Validation & Recording
│   │   ├── report_service.py       # Deliverable 3: Report & Excel Export
│   │   └── ai_service.py           # Deliverable 4: AI Attendance Analyzer
│   └── static/
│       └── index.html              # Dashboard Web Interaktif untuk Demo & Uji Coba
├── tests/
│   └── test_attendance.py          # 14 pengujian otomatis (pytest)
├── requirements.txt
└── .env.example
```

## Cara Menjalankan

1. **Install dependensi** (Python 3.12+):
   ```bash
   pip install -r requirements.txt
   ```
2. *(Opsional)* Salin `.env.example` menjadi `.env` untuk mengatur `SECRET_KEY` atau menambahkan `GEMINI_API_KEY` / `OPENAI_API_KEY`.
3. **Jalankan server FastAPI**:
   ```bash
   uvicorn app.main:app --reload
   ```
4. **Akses aplikasi**:
   - **Dashboard Interaktif**: `http://127.0.0.1:8000/`
   - **Dokumentasi Swagger API**: `http://127.0.0.1:8000/docs`

## Daftar Endpoint Utama

- `GET /attendance/qr/{schedule_id}` — Generate QR Code gambar `image/png` (valid 15 menit).
- `GET /attendance/qr/{schedule_id}/info` — Generate QR Code beserta metadata JSON & base64 PNG.
- `POST /attendance/scan` — Mahasiswa scan QR (`{ "token": "...", "nim": "2301001" }`, opsional `latitude` & `longitude`).
- `GET /attendance/report/student/{nim}` — Persentase kehadiran mahasiswa per mata kuliah.
- `GET /attendance/report/course/{course_id}` — Laporan kelas & daftar mahasiswa `< 75%` (*warning*).
- `GET /attendance/report/course/{course_id}/export` — Download file Excel `.xlsx` untuk dosen.
- `GET /attendance/ai/insights` — Analisis AI otomatis dari data presensi database.
- `POST /attendance/ai/analyze` — Analisis AI dari input JSON array `attendance_records` (Step 3).

## Menjalankan Pengujian Otomatis

```bash
pytest -v
```
