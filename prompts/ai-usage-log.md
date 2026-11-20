# AI Usage Log + OPAR — Modul KRS (Minggu 5–6)

Dokumen ini mencatat penggunaan AI, revisi manual kritis, serta siklus **OPAR** (*Observe, Plan, Act, Reflect*) selama pengerjaan Materi 3 (Modul KRS SEVIMA-Mini).

---

## Log Penggunaan AI — Minggu 5

- **Minggu**: 5
- **Fitur**: Database Schema, Chain of Responsibility Validators, & SQL Query Prasyarat
- **Tujuan**: Membangun 4 tabel utama (`matakuliah`, `krs`, `krs_detail`, `prerequisite`), 4 validator berantai (`SKS`, `Prerequisite`, `Conflict`, `Duplicate`), serta query prasyarat lulus (nilai ≥ C semester sebelumnya) yang cepat dengan index.
- **LLM/Tool**: Antigravity AI Assistant
- **Prompt Kunci**:
  1. *"Implementasikan Chain of Responsibility pattern untuk validasi KRS dengan abstract Validator base class dan 4 turunan: SKSValidator (≤ 24), PrerequisiteValidator (nilai ≥ C semester lalu), ConflictValidator (hari + jam overlap), dan DuplicateValidator (double enrollment). Setiap validator mengembalikan ValidationResult(ok, message) dan rantai berhenti pada kegagalan pertama."*
  2. *"Tulis SQL query untuk mengambil daftar prasyarat matakuliah X yang belum terpenuhi oleh mahasiswa Y (belum lulus dengan nilai ≥ C di semester sebelumnya), lalu rekomendasikan composite index untuk optimasinya."*
  3. *"Tambahkan pengecekan duplicate untuk kelas paralel berbeda yang memiliki kode_induk sama."*
- **Revisi Manual & Penguatan**:
  - Memastikan `ConflictValidator` melewati perbandingan terhadap `kode_mk` yang persis sama, sehingga ketika mahasiswa mencoba mengambil MK duplikat, pesan error tetap dilaporkan oleh `DuplicateValidator` (*double enrollment*), bukan salah dilaporkan sebagai *jadwal bentrok* dengan dirinya sendiri.
  - Memastikan syarat `rn.semester < :semester_sekarang` diterapkan pada query SQL prasyarat agar nilai di semester berjalan tidak dianggap memenuhi prasyarat, serta menangani kasus mahasiswa mengulang MK (nilai `D` di semester 1 lalu lulus `C` di semester 2 tetap sah via `NOT EXISTS`).
  - Menambahkan covering composite index `idx_riwayat_nilai_nim_mk_sem(nim, kode_mk, semester, nilai_huruf)` dan `idx_prerequisite_kode_mk(kode_mk, prasyarat_kode_mk, nilai_minimal)`.
- **Uji & Hasil**: Seluruh unit test validator dan integration test `add_course`/`remove_course` lolos; pesan error spesifik seperti `"Prasyarat tidak terpenuhi: Kalkulus I"` terverifikasi lewat `pytest.raises(..., match=...)`.

### OPAR — Minggu 5
- **Observe**: Query cek prasyarat awalnya melakukan *full table scan* pada `riwayat_nilai` jika tidak ada index, dan `ConflictValidator` dapat bertabrakan dengan `DuplicateValidator` saat kode MK sama persis dimasukkan ulang.
- **Plan**: Gunakan pola `NOT EXISTS` dengan covering index `(nim, kode_mk, semester, nilai_huruf)` dan pisahkan tanggung jawab `ConflictValidator` vs `DuplicateValidator`.
- **Act**: Implementasi query di `app/queries.py`, DDL + index di `sql/schema.sql`, serta unit test edge-case di `tests/test_validators.py`.
- **Reflect**: Covering index membuat pengecekan prasyarat dapat diselesaikan tanpa membaca heap tabel, dan pemisahan tanggung jawab validator menjaga pesan error tetap akurat bagi mahasiswa.

---

## Log Penggunaan AI — Minggu 6

- **Minggu**: 6
- **Fitur**: State Machine KRS, Approval & Revisi Dosen PA, Transaction Management (ACID), Concurrency Control, Property-Based Testing, & KRS Recommendation AI
- **Tujuan**: Memastikan transisi status KRS tidak bisa dilompati (`DRAFT → APPROVED` mustahil), otorisasi 2 lapis (peran + kepemilikan `dosen_pa_id`), approval atomik, aman terhadap *race condition*, dan teruji dengan 1000 kombinasi acak Hypothesis.
- **LLM/Tool**: Antigravity AI Assistant
- **Prompt Kunci**:
  1. *"Gunakan tabel transisi `dict[tuple[KRSStatus, Actor], set[KRSStatus]]` untuk 4 state (DRAFT, SUBMITTED, APPROVED, REVISION). Approve/revise hanya boleh oleh `krs.dosen_pa_id`. Tolak submit jika KRS kosong. Status hanya boleh diubah lewat method `transition()`. Pesan error bahasa Indonesia yang jelas, contoh: `'Transisi tidak diizinkan: DRAFT ke APPROVED'`. Sertakan pytest untuk seluruh 28 transisi ilegal."*
  2. *"Bungkus `approve_krs` dan `revise_krs` dalam satu transaksi ACID (ubah status, catat waktu, tulis LogKRS, tulis Notifikasi ke DB, commit sekali di akhir, rollback jika gagal). Tutup celah konkurensi dengan pessimistic lock `with_for_update()` dan optimistic lock `version_id_col`."*
  3. *"Generate Hypothesis property-based test (1000 contoh, in-memory tanpa DB) yang menguji langsung `SKSValidator` (total ≤ 24 dan penolakan wajib beralasan `total + sks > 24`) dan `ConflictValidator` (diverifikasi dengan oracle slot jam independen)."*
- **Revisi Manual & Penguatan**:
  - **Cek Kepemilikan (`dosen_pa_id`)**: Menambahkan pengecekan lapis ke-2 `if krs.dosen_pa_id != dosen_pa_id: raise ForbiddenError(...)` (HTTP `403`) agar dosen PA lain tidak bisa menyetujui/merevisi KRS mahasiswa yang bukan bimbingannya.
  - **Optimistic Lock pada Mutasi Child Row**: Menambahkan `krs.sentuh_perubahan()` (`diubah_pada = utc_now`) di `add_course` dan `remove_course` karena insert/delete di tabel `krs_detail` tidak otomatis menaikkan `version` pada baris induk `krs`.
  - **Property Test Menguji Sistem, Bukan Generator**: Menulis ulang property test agar memanggil `SKSValidator().validate(ctx)` dan `ConflictValidator().validate(ctx)` langsung di memori tanpa DB, menambahkan assert kedua (penolakan harus beralasan), serta membuat fungsi oracle `_slot_jam()` yang terpisah dari `is_schedule_conflict()`.
  - **Hardcode Spesifikasi Test State Machine**: Menulis ulang 4 transisi sah secara manual di `tests/test_state_machine.py` (tidak mengimpor `TRANSITIONS` dari kode produksi) lalu menguji seluruh 28 kombinasi ilegal.
  - **Guardrail Recommender AI**: Memastikan `KRSRecommendationAgent` tidak menerima begitu saja usulan LLM, melainkan selalu menjalankan `validate_krs()` dan otomatis fallback ke `CSPRecommendationSolver` jika usulan melanggar aturan.
- **Uji & Hasil**: 70 test (termasuk 28 transisi ilegal terparametrize, 2 × 1000 kombinasi acak Hypothesis, test rollback transaksi ACID, test stale version 409, dan test CSP/Agent) semuanya lulus.

### OPAR — Minggu 6
- **Observe**: Pada skenario multi-tab, mahasiswa berpotensi menambahkan mata kuliah pada tab 1 saat tab 2 melakukan `submit_krs` dan dosen PA langsung `approve_krs`, sehingga MK tak tervalidasi bisa menyusup ke KRS berstatus `APPROVED` (*race condition* / *stale screen*).
- **Plan**: Kunci baris `krs` dengan `with_for_update()` di seluruh method mutasi (`add_course`, `remove_course`, `submit_krs`, `approve_krs`, `revise_krs`), periksa status *setelah* kunci didapat, dan tambahkan kolom `version` (`version_id_col`) untuk menolak approval berbasis layar basi dengan HTTP `409 Conflict`.
- **Act**: Memasang `_krs_terkunci()`, `version_id_col`, `sentuh_perubahan()`, validasi `expected_version`, serta integration test rollback & layar basi di `tests/test_krs_service.py` dan `tests/test_krs_api.py`.
- **Reflect**: Pengujian otomatis dengan SQLite in-memory belum membuktikan perilaku *row-level locking* (`SELECT ... FOR UPDATE` diabaikan oleh SQLite). Oleh karena itu, pengujian konkurensi *pessimistic lock* secara paralel perlu diverifikasi manual pada PostgreSQL/MySQL sebelum naik ke produksi.
