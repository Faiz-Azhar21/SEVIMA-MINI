# Panduan Persiapan Viva (Tanpa AI) — Materi 3 Modul KRS

Dosen menegaskan bahwa **State Machine** dan **Transaction Management / Concurrency** hampir pasti ditanyakan saat Viva tanpa bantuan AI. Pahami logika berikut (bukan sekadar menghafal kode):

---

## 1. Bagaimana State Machine Mencegah `DRAFT → APPROVED` Langsung?
1. **Satu Kolom Enum (Bukan Banyak Boolean)**: Status disimpan dalam satu kolom `KRSStatus` (`DRAFT`, `SUBMITTED`, `APPROVED`, `REVISION`), sehingga keadaan mustahil seperti `is_approved=True` & `is_submitted=False` tidak pernah bisa tersimpan.
2. **Tabel Transisi Berprinsip *Default Deny*** (`app/state_machine.py`):
   - Kunci dictionary adalah pasangan `(status_saat_ini, aktor)`, nilainya adalah himpunan status tujuan yang sah.
   - Hanya 4 panah yang terdaftar: `(DRAFT, MAHASISWA) → SUBMITTED`, `(SUBMITTED, DOSEN_PA) → {APPROVED, REVISION}`, dan `(REVISION, MAHASISWA) → SUBMITTED`.
   - Saat memanggil `TRANSITIONS.get((self.status, actor), set())`, pasangan `(DRAFT, DOSEN_PA)` maupun target `APPROVED` dari `DRAFT` tidak ada di himpunan, sehingga otomatis melempar `TransitionError` (HTTP `409 Conflict`).
3. **Enkapsulasi Satu Pintu**: Tidak ada endpoint atau service yang menulis `krs.status = ...` secara langsung; semua perubahan wajib lewat `krs.transition(target, actor)`.
4. **Pemisahan `cek_transisi()` dan `transition()`**: Di `submit_krs()`, kita memanggil `cek_transisi()` *sebelum* `validate_krs()` agar jika status sudah `SUBMITTED`/`APPROVED`, sistem langsung gagal cepat (*fail-fast*) tanpa membuang waktu menjalankan query validasi yang mahal.
5. **Pembuktian Uji**: `tests/test_state_machine.py` membangkitkan seluruh `4 × 4 × 2 = 32` kombinasi `(asal, tujuan, aktor)` dengan `itertools.product`. 4 kombinasi sah di-hardcode langsung dari dokumen tugas (bukan diimpor dari kode!), lalu ke-28 kombinasi ilegal diuji semuanya wajib melempar `TransitionError` tanpa mengubah `krs.status`.

---

## 2. Kenapa `approve_krs` Harus Menjadi Satu Transaksi (ACID)?
Saat dosen PA menyetujui KRS, ada **4 operasi database** yang saling berkaitan:
1. Mengubah `krs.status` menjadi `APPROVED`.
2. Mencatat `krs.approved_at`.
3. Menulis jejak audit di tabel `log_krs` (siapa dosen yang menyetujui dan kapan).
4. Menulis antrean notifikasi di tabel `notifikasi` untuk mahasiswa.

- **Jika tanpa transaksi (commit terpisah)**: Apabila langkah 1 sukses tetapi langkah 3 gagal (mis. koneksi DB putus), KRS tercatat `APPROVED` **tanpa jejak siapa yang menyetujui** (data korup/setengah jadi).
- **Dengan 1 Unit Kerja (ACID)**: Semua perubahan ditumpuk di `session`, lalu `db.commit()` dipanggil **sekali di akhir**. Jika terjadi exception apa pun (termasuk `ForbiddenError` atau DB error), blok `except` memanggil `db.rollback()` sehingga semua batal bersih (*all or nothing* / **Atomicity**).
- **Kenapa notifikasi disimpan ke DB, bukan langsung kirim email?** Karena email yang sudah terkirim ke server SMTP **tidak bisa di-rollback** bila transaksi database gagal sesaat setelahnya. Pengiriman keluar dilakukan *setelah* commit (dengan *Observer Pattern* di Minggu 7–8).

---

## 3. Apa yang Terjadi Jika Dosen Menyetujui Saat Mahasiswa Masih Mengedit?
**Skenario Race Condition**:
Status KRS sedang `REVISION`. Tab 1 mahasiswa memanggil `add_course`, lolos cek status, lalu prosesnya agak lambat. Tab 2 mahasiswa memanggil `submit_krs`, lalu dosen PA langsung `approve_krs`. Saat Tab 1 selesai menulis ke DB, mata kuliah yang belum divalidasi saat submit bisa masuk ke KRS yang sudah `APPROVED`.

**Dua Lapis Pengamanan yang Diterapkan**:
1. **Pessimistic Lock (`SELECT ... FOR UPDATE`)**:
   - Semua method yang mengubah KRS (`add_course`, `remove_course`, `submit_krs`, `approve_krs`, `revise_krs`) wajib mengunci baris `krs` yang sama terlebih dahulu lewat `_krs_terkunci()` dan memeriksa `status` **setelah** kunci diperoleh.
   - Request kedua terpaksa menunggu hingga transaksi pertama selesai (`commit`/`rollback`), lalu melihat status terbaru (`SUBMITTED`/`APPROVED`) dan langsung ditolak (`409`).
2. **Optimistic Lock (`version` / `version_id_col`)**:
   - Melindungi dari **layar basi (*stale screen*)**: dosen membuka halaman saat `version = 2`, mahasiswa sempat mengubah MK (kita memanggil `krs.sentuh_perubahan()` agar `version` naik ke `3` meski yang berubah adalah tabel anak `krs_detail`), lalu dosen menekan approve dengan membawa `version = 2`.
   - Sistem mendeteksi versi tidak cocok (`expected_version != krs.version` atau `StaleDataError`) dan menolak dengan HTTP `409 Conflict` (`"KRS sudah berubah, muat ulang"`).

---

## 4. Poin Tambahan yang Sering Ditanyakan
- **Perbedaan HTTP `403` vs `409` vs `400` vs `422`**:
  - `403 Forbidden`: **orangnya salah** (bukan `krs.dosen_pa_id` pemilik).
  - `409 Conflict`: **orangnya benar, tapi state/versinya salah** (transisi ilegal, KRS terkunci, atau versi basi).
  - `400 Bad Request`: **aturan bisnis gagal** (SKS > 24, prasyarat tidak terpenuhi, bentrok jadwal, KRS kosong).
  - `422 Unprocessable Entity`: **input wajib tidak valid** (catatan revisi kosong).
- **Mengapa 1 Exception Handler Cukup (Polimorfisme OOP)?**
  `ForbiddenError`, `TransitionError`, `KRSLockedError`, `NotFoundError`, dan `ValidationInputError` semuanya mewarisi `KRSError` dan menimpa atribut kelas `status_code`. FastAPI cukup mendaftarkan satu handler untuk `KRSError` dan membaca `exc.status_code`.
- **Jebakan Property-Based Testing**:
  1. Tidak boleh hanya `assert sum(courses) <= 24` atau memfilter generator — harus menguji `SKSValidator` sistem kita.
  2. Wajib ada **assert kedua** (`assert total_sebelum + sks > 24` saat ditolak), kalau tidak, validator cacat yang selalu mengembalikan `False` juga akan lulus test!
  3. Untuk bentrok jadwal, pemeriksaan hasil wajib memakai **oracle independen** (`_slot_jam` berbasis himpunan jam), bukan memanggil ulang `is_schedule_conflict()` milik validator sendiri.
  4. Dijalankan **in-memory tanpa DB** agar 1000 contoh selesai dalam hitungan detik dan tidak terbentur masalah reset fixture `pytest`.
