# ADR-001: Perilaku Rantai Validasi KRS, Urutan Validator, dan Kebijakan Jadwal Bersambung

- **Status**: Accepted
- **Tanggal**: 2026-11-20
- **Konteks Modul**: SEVIMA-Mini — Materi 3 Minggu 5 (Modul KRS)

---

## 1. Konteks

Sistem pengisian KRS memiliki empat aturan bisnis inti:
1. Tidak boleh mengambil mata kuliah yang sama dua kali (*double enrollment*).
2. Total SKS per semester maksimal 24 (`<= 24`).
3. Seluruh mata kuliah prasyarat harus sudah lulus (nilai >= C) pada semester sebelumnya.
4. Jadwal antar mata kuliah tidak boleh bertumpuk (*conflict*).

Saat menerjemahkan spesifikasi tugas (PDF) dan rancangan *sequence diagram* (Minggu 2) ke dalam pola **Chain of Responsibility**, muncul tiga keputusan arsitektural utama yang saling memengaruhi performa, *user experience* (UX), dan pemeliharaan kode:
1. Apakah validasi harus **berhenti pada kegagalan pertama (*fail-fast*)** atau **mengumpulkan semua kesalahan (*collect-all*)**?
2. Bagaimana **urutan validator** yang paling tepat di dalam rantai?
3. Apakah dua mata kuliah yang waktunya tepat **bersambung** (mis. `08:00–10:30` dan `10:30–12:00`) dianggap bentrok atau diperbolehkan?

---

## 2. Keputusan

### Keputusan A: Hibrida — *Fail-Fast* di `add_course()`, *Collect-All* di `validate_krs()`
- Pada **`add_course(nim, kode_mk)`**, sistem menjalankan rantai `self.chain.validate(ctx)` yang **berhenti pada kegagalan pertama (*fail-fast*)**, sesuai spesifikasi Step 1.
- Pada **`validate_krs(nim)`**, sistem mengiterasi setiap `KRSDetail` dan memanggil `v.check(ctx)` secara langsung pada seluruh validator (tanpa memutus rantai), lalu mengumpulkan dan menduplikasi-bersih seluruh pesan kegagalan (*collect-all*) sebelum mahasiswa melakukan *submit*.

### Keputusan B: Urutan Rantai `Duplicate → SKS → Prerequisite → Conflict`
- Urutan default di `default_validators()` disusun dari pemeriksaan paling murah secara komputasi dan paling relevan secara pesan kesalahan menuju pemeriksaan yang membutuhkan query DB atau iterasi lebih berat:
  1. `DuplicateValidator` — *in-memory* `O(n)`, tanpa query DB.
  2. `SKSValidator` — *in-memory* `O(n)`, tanpa query DB (data `matakuliah` sudah di-*eager load*).
  3. `PrerequisiteValidator` — menjalankan 1 query SQL `NOT EXISTS` terindeks.
  4. `ConflictValidator` — iterasi perbandingan interval jadwal *in-memory*.

### Keputusan C: Jadwal Bersambung Diperbolehkan (`<`, bukan `<=`)
- Rumus deteksi bentrok menggunakan irisan interval terbuka di ujung:
  ```python
  a.hari == b.hari and a.jam_mulai < b.jam_selesai and b.jam_mulai < a.jam_selesai
  ```
- Kuliah yang selesai pukul `10:30` dan kuliah berikutnya yang mulai pukul `10:30` **tidak dianggap bentrok**.

---

## 3. Alternatif & Trade-off

### Terhadap Keputusan A (*Fail-Fast* vs *Collect-All*)
| Alternatif | Kelebihan | Kekurangan |
| :--- | :--- | :--- |
| **Selalu *Fail-Fast* di semua method** | Paling sederhana; hemat query DB. | Buruk untuk UX saat validasi KRS utuh sebelum *submit* — mahasiswa harus memperbaiki error satu per satu dan berulang kali klik validasi. |
| **Selalu *Collect-All* di semua method** | Mahasiswa selalu mendapat daftar lengkap error. | Pada `add_course()` (tambah 1 MK), query prasyarat yang relatif mahal tetap dieksekusi meskipun MK tersebut sudah duplikat atau melebihi batas SKS; tidak sesuai spesifikasi Step 1 ("Chain berhenti saat ada failure"). |
| **Hibrida (Dipilih)** | Cepat dan hemat resource saat `add_course()`, namun tetap informatif saat `validate_krs()`. | `KRSManager` menyimpan `self.validators` sekaligus `self.chain`, dan `validate_krs()` perlu deduplikasi pesan error lintas MK. |

### Terhadap Keputusan B (Urutan Validator)
| Alternatif | Kelebihan | Kekurangan |
| :--- | :--- | :--- |
| **Urutan daftar PDF (`SKS → Prerequisite → Conflict → Duplicate`)** | Mengikuti urutan penulisan bullet di dokumen tugas secara literal. | Jika mahasiswa sudah punya 22 SKS dan tidak sengaja klik ulang MK 3 SKS yang sudah ada di KRS, pesan yang muncul malah *"Total SKS 25 melebihi batas 24"* padahal akar masalahnya adalah duplikasi. |
| **`Duplicate → SKS → Prerequisite → Conflict` (Dipilih)** | Pesan paling akurat saat salah klik duplikat; dua cek termurah (tanpa SQL) berada di depan sehingga query `NOT EXISTS` tidak dijalankan sia-sia bila sudah gagal duplikat/SKS. | Urutan berbeda dari bullet list PDF (sehingga wajib didokumentasikan secara eksplisit di ADR ini). |

### Terhadap Keputusan C (Jadwal Bersambung)
| Alternatif | Kelebihan | Kekurangan |
| :--- | :--- | :--- |
| **Strict (`<=`) atau wajib jeda 15 menit** | Memberi waktu pindah gedung antar kelas. | Menolak banyak jadwal kampus yang secara resmi memang disusun bersambung (mis. sesi 1 `08:00–10:30`, sesi 2 `10:30–13:00`). |
| **Irisan interval `<` (Dipilih)** | Sesuai praktik umum penjadwalan sesi kuliah standar; sederhana dan deterministik. | Jika di masa depan kampus mewajibkan jeda pindah gedung (mis. 10 menit), fungsi `bentrok()` perlu ditambahkan parameter buffer. |

---

## 4. Konsekuensi

1. **Kepatuhan SOLID (SRP & OCP)**: `KRSManager` tidak perlu diubah apabila di masa depan kampus menambah validator baru (mis. `TunggakanSPPValidator`) atau mengubah urutan prioritas rantai—cukup suntikkan daftar validator berbeda lewat constructor `KRSManager(db, validators, semester)`.
2. **Testability Tinggi**: Setiap validator dapat diuji secara unit terisolasi melalui `.check(ctx)`, sementara perilaku *fail-fast* diuji lewat `build_chain(...).validate(ctx)`.
3. **Deduplikasi Error Simetris**: Karena `validate_krs()` memeriksa setiap MK terhadap MK lain, konflik pasangan `(A, B)` dan `(B, A)` dinormalisasi kunci deduplikasinya agar mahasiswa hanya melihat satu laporan per pasangan bentrok.
4. **Defense in Depth**: Meskipun `DuplicateValidator` berada di urutan pertama aplikasi, constraint database `UNIQUE(krs_id, kode_mk)` tetap dipertahankan sebagai jaring pengaman terakhir jika terjadi *race condition*.
