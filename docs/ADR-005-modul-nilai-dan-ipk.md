# ADR-005: Arsitektur Modul Nilai, Perhitungan IPS/IPK, dan Audit Trail (Minggu 9)

- **Status**: Diterima (*Accepted*) — dengan 1 *Open Question* terkait batas kelulusan huruf `D`
- **Tanggal**: 2026-11-22
- **Konteks**: Materi 5 Minggu 9 (SEVIMA-Mini — Modul Nilai & Transkrip, Bagian 1)

---

## Keputusan 1: Satu Grade = Satu Baris `krs_detail` (Tanpa Tabel `grades` Terpisah)

- **Konteks**: Dokumen tugas menyebut tabel `grades`, namun sejak Minggu 5 tabel `krs_detail` sudah memiliki kolom `nilai` (dibaca oleh query prasyarat) dan sejak Minggu 7 memiliki kolom `kelas_id`.
- **Keputusan**: Nilai tetap disimpan pada `krs_detail.nilai` dengan penambahan *Foreign Key* `krs_detail.nilai → skala_nilai.huruf` (`fk_krs_detail_nilai_skala_nilai`). Kolom `grade_history.grade_id` merujuk ke `krs_detail.id` (nama kolom `grade_id` dipertahankan agar sesuai dengan dokumen tugas).
- **Alasan**: Menghindari **dua sumber kebenaran** (*two sources of truth*) antara tabel `grades` baru dan `krs_detail.nilai` yang sudah digunakan modul KRS/Prasyarat Minggu 5.
- **Konsekuensi**: Huruf nilai yang tidak dikenal ditolak langsung oleh *database* (ketika FK aktif), selain validasi awal oleh Pydantic di API.

---

## Keputusan 2: Aturan Kelulusan Disimpan sebagai Data (`skala_nilai.lulus`) & Asumsi Sementara Minimal C

- **Konteks**: Ditemukan kontradiksi spesifikasi pada dokumen tugas: *"Lulus MK jika nilai ≥ D (2.0)"*, padahal `D = 1.00` dan `C = 2.00`.
- **Keputusan**:
  1. Menambahkan kolom `lulus: Boolean` pada tabel `skala_nilai` dan meningkatkan tipe `bobot` menjadi `Numeric(3, 2)`.
  2. Menggunakan asumsi sementara **minimal C (`2.00`)** (`A, B, C → lulus=True`; `D, E → lulus=False`) agar konsisten dengan aturan prasyarat Minggu 5.
  3. Mengajukan klarifikasi tertulis ke stakeholder (`docs/pertanyaan-stakeholder-m9.md`).
- **Alasan**: Memisahkan kebijakan akademik (*data*) dari logika program (*code*). Jika stakeholder memutuskan `D` lulus, cukup mengubah 1 baris di `skala_nilai` tanpa mengubah kode `hitung_ipk`.

---

## Keputusan 3: Compute-on-Read untuk IPK (Tidak Menyimpan Kolom Cache IPK)

- **Konteks**: Kriteria sukses mensyaratkan *"IPK ter-update otomatis saat nilai diinput"*.
- **Keputusan**: Memilih **compute-on-read** — IPK tidak disimpan pada kolom tabel `mahasiswa`, melainkan dihitung langsung setiap kali dibaca dari `krs_detail` menggunakan fungsi murni `hitung_ipk` dan dikirim via JSON sebagai **string** (mis. `"3.08"`).
- **Alasan**:
  - Sumber kebenaran tunggal (`krs_detail`) → IPK **tidak pernah basi** (*stale*) walaupun ada koreksi data lewat SQL manual.
  - Seorang mahasiswa paling banyak memiliki ~60 baris nilai sepanjang studi; satu query terindeks pada `krs.nim` selesai dalam hitungan milidetik.
- **Rencana Evolusi**: Jika suatu hari dibutuhkan laporan IPK massal untuk ribuan mahasiswa sekaligus, caching akan ditambahkan dengan pola **Outbox + Observer** (Minggu 8): `GradeService` menulis event `NILAI_CHANGED` ke tabel outbox dalam transaksi yang sama, lalu observer menghitung ulang cache setelah *commit*.

---

## Keputusan 4: Pencatatan Audit Trail di `GradeService` dalam Satu Transaksi Atomik (Bukan DB Trigger)

- **Konteks**: Dokumen tugas menyebut trigger `UPDATE` untuk menulis ke `grade_history`.
- **Keputusan**: Audit trail dicatat langsung oleh `GradeService.input_nilai()` di dalam **satu transaksi database yang sama** dengan perubahan `krs_detail.nilai` (termasuk pencatatan input perdana dengan `old_value = NULL`). Tabel `grade_history` bersifat *append-only*. View `v_riwayat_nilai` disediakan untuk membaca riwayat per mahasiswa.
- **Alasan**:
  - `GradeService` memiliki konteks lengkap mengenai aktor (`changed_by = dosen_id` dari login) dan `reason` tanpa bergantung pada *session variable* spesifik DBMS.
  - Logika eksplisit terlihat di kode dan portabel antara SQLite (pengujian) dan PostgreSQL/MySQL (produksi).
- **Larangan Penting**: **Tidak menggunakan DB Trigger bersamaan dengan logging di Service**, karena akan mengakibatkan **jejak ganda** (*double logging*) pada setiap perubahan nilai.
- **Trade-off**: Perubahan manual langsung lewat konsol SQL tidak tercatat; di produksi akses tulis manual ke `krs_detail` harus dibatasi dan hak `UPDATE`/`DELETE` pada `grade_history` dicabut bagi user aplikasi.

---

## Keputusan 5: Presisi `Decimal` (`ROUND_HALF_UP`) & Dependency Inversion untuk Presensi

- **Presisi Numerik**: Seluruh bobot dan agregasi IPS/IPK menggunakan `decimal.Decimal` (dikonstruksi dari `str`/`int`, bukan `float`) dengan pembulatan `ROUND_HALF_UP` dua desimal **sekali di akhir** agar kasus seperti `25/8 = 3.125` dibulatkan ke `3.13` (bukan `3.12` *banker's rounding* dari `round()` Python).
- **PresensiPort & PresensiStub**: Karena modul Presensi baru dibangun di Minggu 12, `GradeService` hanya bergantung pada protokol `PresensiPort`. Saat ini disuntikkan `PresensiStub` lewat *dependency injection*; di Minggu 12 cukup mengganti implementasi adapter tanpa memodifikasi `GradeService`.
