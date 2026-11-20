# AI Usage Log — Materi 3 (Minggu 5: Modul KRS)

Dokumen ini mencatat penggunaan AI secara transparan sesuai **AI-First Charter**:
- **Privasi Data**: Seluruh prompt dan pengujian hanya menggunakan **data dummy** (Budi Santoso, Ani Wijaya, Citra Lestari, Kalkulus I, Algoritma, dll.) — tidak pernah menempelkan data mahasiswa sungguhan.
- **Akuntabilitas**: Setiap baris kode hasil bantuan AI direview terhadap checklist jebakan klasik dan diverifikasi dengan unit/integration test.

---

## 1. Ringkasan Prompt Kunci & Konteks yang Diberikan

### Prompt 1 — Skema SQLAlchemy 2.0 & Migrasi Alembic
- **Tujuan**: Merancang 4 tabel inti (`matakuliah`, `prerequisite`, `krs`, `krs_detail`), tabel bantu `skala_nilai`, serta tabel minimal `calon_mahasiswa` dari Modul PMB.
- **Konteks yang ditambahkan ke prompt**:
  - Python 3.12, SQLAlchemy 2.0 (`Mapped` / `mapped_column`), Alembic.
  - Relasi *self-referencing many-to-many* eksplisit (`primaryjoin` & `secondaryjoin`).
  - Format `semester` fixed-length 5 karakter (`"20251"`).
  - `UNIQUE(nim, semester)`, `UNIQUE(krs_id, kode_mk)`, `CHECK` constraint (`sks BETWEEN 1 AND 4`, `jam_mulai < jam_selesai`, `kode_mk <> kode_prasyarat`).
  - `cascade="all, delete-orphan"` pada `KRS.details`.

### Prompt 2 — Chain of Responsibility Validator (Step 1)
- **Tujuan**: Membangun `ValidationResult`, `KRSContext`, `Validator(ABC)`, `build_chain`, serta 4 validator (`DuplicateValidator`, `SKSValidator`, `PrerequisiteValidator`, `ConflictValidator`).
- **Konteks yang ditambahkan ke prompt**:
  - Satu konstanta `MAX_SKS = 24` (*single source of truth*), batas `<= 24` (tolak hanya jika `> 24`).
  - Rumus irisan interval jadwal (`a.hari == b.hari and a.jam_mulai < b.jam_selesai and b.jam_mulai < a.jam_selesai`).
  - Pesan error spesifik menyebut nama mata kuliah / angka SKS (contoh: `"Prasyarat tidak terpenuhi: Kalkulus I"`).
  - Urutan rantai default `Duplicate → SKS → Prerequisite → Conflict`.

### Prompt 3 — Query SQL Prasyarat & Optimasi Index (Step 3)
- **Tujuan**: Menulis query `NOT EXISTS` untuk mengembalikan daftar prasyarat yang belum lulus (`nilai >= C`) pada semester sebelumnya dan membuktikan performa index via `EXPLAIN`.
- **Konteks yang ditambahkan ke prompt**:
  - Pemetaan bobot numerik lewat tabel `skala_nilai` (`s.bobot >= 2.00`), **bukan** perbandingan string `d.nilai >= 'C'`.
  - Parameterized query (`:nim`, `:kode_mk`, `:semester`) untuk keamanan SQL injection.
  - Pembuktian `EXPLAIN QUERY PLAN` (sebelum vs sesudah index pada 10.000 baris dummy `krs_detail`).

### Prompt 4 — `KRSManager` Service, Concurrency, & API FastAPI
- **Tujuan**: Membangun `KRSManager` (*SRP*, bebas HTTP, *Dependency Injection* validator) dengan `with_for_update()`, 1 transaksi commit di akhir, guard `EDITABLE = {DRAFT, REVISION}`, serta router FastAPI tipis.

---

## 2. Checklist Code Review & Revisi yang Dilakukan

| No | Potensi Jebakan AI | Hasil Pemeriksaan & Revisi yang Diterapkan | Lokasi Bukti |
| :---: | :--- | :--- | :--- |
| 1 | **Deteksi bentrok hanya `a.jam_mulai == b.jam_mulai`** | Dipastikan menggunakan irisan interval `a.jam_mulai < b.jam_selesai and b.jam_mulai < a.jam_selesai`; diuji dengan 5 kasus uji (sebagian, di dalam, persis sama, bersambung, beda hari). | `app/validators/krs.py`, `tests/test_validators.py` |
| 2 | **Perbandingan nilai huruf sebagai string (`d.nilai >= 'C'`)** | Ditolak. Diganti dengan `JOIN skala_nilai s ON s.huruf = d.nilai` dan `s.bobot >= 2.00`; diuji khusus bahwa nilai `A`, `B`, `C` lulus sedangkan `D`, `E`, `NULL` gagal. | `app/queries/prerequisite.py`, `tests/test_validators.py` |
| 3 | **Arah *self-referencing join* `prerequisite` tertukar** | Diverifikasi eksplisit: `primaryjoin` ke `prerequisite.c.kode_mk`, `secondaryjoin` ke `prerequisite.c.kode_prasyarat`. Dibuktikan dengan unit test `sd.prasyarat == [algoritma]` dan `algoritma.prasyarat == []`. | `app/models/krs.py`, `tests/test_models.py` |
| 4 | **Off-by-one batas SKS (`total >= 24`)** | Dipastikan menggunakan `total > self.max_sks` sehingga total tepat **24 SKS masih diizinkan**, sedangkan **25 SKS ditolak**. | `app/validators/krs.py`, `tests/test_validators.py` |
| 5 | **Query N+1 di dalam loop `ctx.details`** | Revisi penting: `_krs_terkunci()` menggunakan `options(selectinload(KRS.details).joinedload(KRSDetail.matakuliah))` sehingga seluruh `MataKuliah` termuat sebelum masuk loop validator, sekaligus aman dipakai bersama `with_for_update()`. | `app/services/krs_manager.py` |
| 6 | **Kebocoran konsep HTTP ke lapisan Service** | Revisi desain: `KRSManager` hanya melempar domain exception (`KRSError`, `KRSNotFoundError`, `KRSStateError`, `KRSValidationError`), sedangkan mapping ke status HTTP (`400`, `404`, `409`) sepenuhnya ditangani di `app/api/krs.py`. | `app/services/krs_manager.py`, `app/api/krs.py` |
| 7 | **SQLite FK off secara default & `FOR UPDATE` diabaikan SQLite** | Menambahkan listener `PRAGMA foreign_keys=ON` di `app/database.py` agar integritas FK aktif di SQLite, dan mendokumentasikan keharusan verifikasi row lock di MySQL pada `README.md`. | `app/database.py`, `README.md` |
| 8 | **Bentrok simetris muncul dua kali di `validate_krs()`** | Revisi pada `KRSManager._dedup_key()` agar bentrok antara MK A dan MK B hanya dilaporkan sekali saat `validate_krs()` mengumpulkan semua error. | `app/services/krs_manager.py`, `tests/test_krs_manager.py` |

---

## 3. Poin Kesiapan Penjelasan (*Viva*)

1. **Mengapa `Enrollment` dipecah menjadi `krs` dan `krs_detail`?** Agar status persetujuan (`DRAFT/SUBMITTED/APPROVED/REVISION`) dan `dosen_pa_id` dijaga di level kartu (1 tempat), mencegah anomali KRS setengah disetujui.
2. **Mengapa `add_course()` mengunci baris `KRS` dengan `with_for_update()`?** Mencegah *race condition* "2 tab, 1 detik, 27 SKS" saat dua request membaca total 21 SKS secara bersamaan dan sama-sama lolos `SKSValidator`.
3. **Mengapa urutan kolom `UNIQUE(nim, semester)` penting?** Pada B-Tree index, kolom kesetaraan (`nim =`) harus berada di depan kolom rentang (`semester <`) agar query pencarian semester sebelumnya dapat memanfaatkan index secara optimal.
4. **Mengapa `KRSManager` menerima `validators` lewat constructor?** Penerapan *Dependency Injection* dan *Open/Closed Principle*: memudahkan penggantian/mock validator saat testing serta penambahan aturan baru tanpa memodifikasi `KRSManager`.
