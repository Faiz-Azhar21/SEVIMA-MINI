# AI Usage Log: Implementasi Modul PMB (Penerimaan Mahasiswa Baru)

Dokumen ini mencatat log penggunaan AI, prompt engineering, arsitektur sistem, dan pertimbangan teknis dalam pengerjaan modul PMB berbasis FastAPI, SQLAlchemy, dan Alembic.

---

## 1. Ringkasan Tugas & Tujuan Pembelajaran
- **Modul**: PMB (Penerimaan Mahasiswa Baru) Minggu 3-4.
- **Tujuan**:
  1. Implementasi class diagram / UML ke kode OOP (SQLAlchemy Models).
  2. Membangun REST API dengan FastAPI.
  3. Validasi input dengan constraint database (unique email, nomor telepon format Indonesia, enum status).
  4. Generator identifier unik (NIM) dengan format institusional: `[Tahun:4][Kode Prodi:3]-[Running Number:4]` yang bersifat **idempotent** dan **thread-safe**.
  5. Menulis skrip migrasi database dengan rollback (Alembic).
  6. Mengembangkan unit tests dengan Pytest dengan target coverage > 80% (tercapai **94%**).

---

## 2. Log Penggunaan AI per Langkah Pengerjaan

### Step 1: Prompt untuk Database Schema & Migrasi
* **Prompt yang Diberikan:**
  > *"Desain skema database PMB untuk sistem akademik:*
  > *Tabel `calon_mahasiswa`: id, nama_lengkap, email (unique), phone, tanggal_lahir, alamat, program_studi_id, jalur_masuk (SNBP/SNBT/Mandiri), status (pending/approved/rejected), created_at, approved_at.*
  > *Tabel `program_studi`: id, kode (3 char), nama, fakultas.*
  > *Tabel `jalur_masuk`: id, kode, nama, keterangan.*
  > *Buat SQLAlchemy model + Alembic migration script.*
  > *Tambahkan constraint phone format Indonesia dan email validation."*

* **Rekomendasi & Keputusan Desain:**
  - **Tabel `program_studi`**: Menyimpan master data program studi (`kode` 3 karakter unik, misal `001` untuk Teknik Informatika).
  - **Tabel `jalur_masuk`**: Normalisasi master data jalur penerimaan (`SNBP`, `SNBT`, `Mandiri`).
  - **Tabel `calon_mahasiswa`**:
    - `email`: Menggunakan constraint `unique=True` dan index pencarian cepat.
    - `phone`: Ditambahkan SQL `CheckConstraint` untuk validasi format nomor Indonesia (`08%`, `+62%`, `62%`) serta Pydantic Regex Validator (`^(\+62|62|08)[0-9]{8,13}$`).
    - `status`: Enum constraint (`pending`, `approved`, `rejected`) dengan default value `pending`.
    - `nim`: String(20) nullable unique, diisi saat admin melakukan *approval*.
  - **Alembic Migration**: Dibuat file versi `001_initial_pmb_schema.py` yang memiliki fungsi `upgrade()` dan `downgrade()` untuk mendukung mekanisme rollback skema database secara aman.

---

### Step 2: Generate API Endpoints
* **Prompt yang Diberikan:**
  > *"Buat FastAPI endpoint untuk PMB:*
  > *1. POST /register: terima JSON calon mahasiswa, validasi input, simpan dengan status 'pending'*
  > *2. PUT /approve/{id}: ubah status jadi 'approved', generate NIM format [tahun][kode_prodi][sequential], return NIM*
  > *3. GET /status/{id}: return data pendaftar + status*
  > *Sertakan error handling (404, 400, 409 conflict).*
  > *Buat dependency injection untuk DB session."*

* **Rekomendasi & Keputusan Desain:**
  - **Dependency Injection**: Menggunakan `db: Session = Depends(get_db)` dengan generator session FastAPI yang mengelola lifecycle koneksi DB secara otomatis.
  - **Error Handling**:
    - `409 Conflict`: Dikeluarkan saat calon mahasiswa mendaftar dengan email yang sudah ada di database (`duplicate email`).
    - `400 Bad Request`: Dikeluarkan saat format nomor HP salah, format email tidak valid, atau ID program studi / jalur masuk tidak ditemukan. Dibuat custom exception handler untuk `RequestValidationError` agar FastAPI mengembalikan status 400 (bukan 422 bawaan).
    - `404 Not Found`: Dikeluarkan saat pendaftar dengan ID tertentu tidak ditemukan saat cek status maupun approve.
  - **Dual Routing Prefix**: Router didaftarkan baik di `/api/pmb/...` maupun alias `/...` agar mendukung fleksibilitas pemanggilan endpoint.

---

### Step 3: Implementasi NIM Generator (Thread-Safe & Idempotent)
* **Prompt yang Diberikan:**
  > *"Buat function generate_nim yang thread-safe*
  > *def generate_nim(tahun: int, kode_prodi: str, db: Session) -> str:*
  > *Generate NIM format: YYYY[KODE]XXXX*
  > *Example: 2025001-0001"*

* **Analisis Race Condition & Solusi Konkurensi:**
  - **Masalah Race Condition**: Jika dua request approve untuk prodi yang sama datang bersamaan pada sistem multi-thread atau multi-worker, keduanya dapat membaca sequential number yang sama (misal 1) dan mencoba membuat NIM yang sama (`2025001-0001`), menghasilkan *duplicate key error* atau data korup.
  - **Solusi yang Diterapkan**:
    1. **Reentrant Lock (`threading.RLock`)**: Menggunakan mutual exclusion lock level proses untuk menyinkronkan akses ke pembuatan sequence dan penyimpanan record calon mahasiswa. Digunakan `RLock` agar fungsi `approve_calon_mahasiswa` dapat memanggil `generate_nim` tanpa mengalami *deadlock*.
    2. **Atomic Sequence Generation**: Query mengambil NIM tertinggi dengan prefix tahun dan kode prodi terkait (`filter(CalonMahasiswa.nim.like(f"{prefix}%"))`), mengurai suffix nomor urut, dan menambahkan 1 secara atomic.
    3. **Idempotency**: Jika pendaftar sudah berstatus `approved` dan telah memiliki `nim`, pemanggilan ulang endpoint `PUT /approve/{id}` tidak akan mengubah nomor urut atau menghasilkan NIM baru, melainkan mengembalikan NIM yang sudah ada.

---

### Step 4: Testing Strategy & Kualitas Kode
* **Prompt yang Diberikan:**
  > *"Generate pytest untuk modul PMB:*
  > *- test_register_success: data valid, return 201*
  > *- test_register_duplicate_email: return 409 conflict*
  > *- test_approve_generate_nim: NIM sesuai format dan sequential*
  > *- test_approve_idempotent: approve 2x tidak generate NIM baru*
  > *- test_invalid_phone_format: return 400*
  > *Gunakan pytest fixtures untuk setup database."*

* **Hasil Pengujian**:
  - Dibuat fixture `test_engine` dan `test_db` dengan SQLite in-memory yang menggunakan `StaticPool` agar thread testing dapat mengakses memory database yang sama secara konsisten.
  - Seluruh skenario uji lulus 100% (**19 passed**).
  - Tingkat cakupan kode (**Test Coverage**) mencapai **94%** (melampaui syarat minimal 80%).

---

## 3. Matriks Kriteria Sukses

| Kriteria | Target | Status | Keterangan |
| :--- | :---: | :---: | :--- |
| Form registrasi bisa diakses via browser/Postman | Ya | ✅ Terpenuhi | Halaman UI di `/`, Swagger UI di `/docs`, dan Postman di `/api/pmb/register` |
| Duplicate email ditolak sistem | 409 Conflict | ✅ Terpenuhi | Teruji di `test_register_duplicate_email` |
| NIM tergenerate otomatis saat approve | Format Institusional | ✅ Terpenuhi | Format `2025001-0001` sequential teruji |
| Idempotency Approval | Tidak ganti NIM | ✅ Terpenuhi | Teruji di `test_approve_idempotent` |
| Test coverage minimal | >= 80% | ✅ Terpenuhi | **94% Total Coverage** |
| API Documentation | Swagger & ReDoc | ✅ Terpenuhi | Tersedia di `/docs` dan `/redoc` |
| Database Migration & Rollback | Alembic | ✅ Terpenuhi | Berhasil upgrade ke head dan downgrade rollback ke base |
