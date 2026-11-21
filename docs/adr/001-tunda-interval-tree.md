# ADR 001: Menunda Optimasi Interval Tree dan Menggunakan Grouping + Sort & Sweep

- **Status**: Diterima (Minggu 7)
- **Tanggal**: 2026-11-20
- **Modul**: SEVIMA-Mini — Modul Jadwal & Ruangan (`app/services/conflict.py`)

---

## 1. Konteks

Dokumen spesifikasi tugas (Step 1) menyarankan optimasi pengecekan tumpang tindih jam menggunakan struktur data **Interval Tree** (`O(log n + k)` per query) sebagai alternatif pendekatan naif `O(n^2)`.

Dalam sistem akademik SEVIMA-Mini, operasi deteksi bentrok muncul dalam dua pola berbeda:
1. **Validasi 1 jadwal baru/ubah (`POST`/`PUT /api/jadwal`)**: Dilakukan langsung di database menggunakan query SQL dengan *composite index* `ix_jadwal_ruangan(hari, ruangan_kode)` dan `ix_jadwal_dosen(hari, dosen_id)`.
2. **Audit menyeluruh seluruh jadwal (`GET /api/jadwal/conflicts` dan detektor batch)**: Memeriksa seluruh daftar jadwal satu semester (skala kampus tipikal ~400–600 jadwal per semester; setelah dikelompokkan per `(hari, ruangan)` hanya tersisa ~6–8 jadwal per grup).

Prinsip rekayasa yang digunakan: **optimasi tanpa pengukuran hanyalah tebakan yang terdengar canggih.**

---

## 2. Pengukuran Empiris

Benchmark dijalankan menggunakan `python -m scripts.benchmark_conflict` (Python 3.12, median dari 5 kali eksekusi per ukuran dataset, distribusi 6 hari dengan jumlah ruangan dan dosen proporsional):

| Jumlah Jadwal (`N`) | Jumlah Pasangan | Konflik Ditemukan | `detect_naive` (`O(n^2)`) | `detect_schedule_conflict` (Sweep, `O(n log n + k)`) | Speedup | Output Identik? |
| ---: | ---: | ---: | ---: | ---: | ---: | :---: |
| 40 | 780 | 8 | 0.046 ms | 0.060 ms | 0.8× | Ya (`True`) |
| 200 | 19,900 | 149 | 1.082 ms | 0.276 ms | 3.9× | Ya (`True`) |
| **600** *(1 kampus, 1 smt)* | **179,700** | **774** | **10.024 ms** | **1.040 ms** | **9.6×** | **Ya (`True`)** |
| 2,000 | 1,999,000 | 2,448 | 108.304 ms | 3.383 ms | 32.0× | Ya (`True`) |
| 5,000 | 12,497,500 | 6,095 | 712.259 ms | 13.409 ms | 53.1× | Ya (`True`) |

**Temuan kunci:**
- Pada skala nyata 1 kampus 1 semester (`N = 600`), Grouping + Sort & Sweep selesai dalam **~1.04 ms** (9.6× lebih cepat dari naif) menggunakan *pure Python* tanpa pustaka eksternal.
- Bahkan pada `N = 5,000` (8× lebih besar dari skala kampus target), waktu eksekusi masih **13.4 ms** — jauh di bawah latensi jaringan atau query database.
- Karena 1 ruangan dalam 1 hari hanya berisi ~6–8 sesi kuliah, overhead membangun struktur pohon Interval Tree (`intervaltree` / pohon seimbang manual) justru tidak memberi keuntungan berarti dan menambah dependensi eksternal.

---

## 3. Keputusan

1. **Menggunakan Grouping + Sort & Sweep (`O(n log n + k)`)** sebagai implementasi produksi di `detect_schedule_conflict()`.
2. **Mempertahankan `detect_naive()` (`O(n^2)`)** sebagai *oracle/pembanding* untuk *differential testing* berbasis Hypothesis (`Counter(sweep) == Counter(naive)`).
3. **Menunda penggunaan Interval Tree** pada Minggu 7 hingga terdapat beban kerja yang benar-benar membutuhkannya.
4. Untuk operasi *single-write* (`POST`/`PUT`), tetap mengandalkan **query SQL berindeks** (`ix_jadwal_ruangan` dan `ix_jadwal_dosen`) yang dieksekusi di dalam transaksi terkunci (`with_for_update()`).

---

## 4. Konsekuensi

**Positif:**
- Tidak menambah dependensi pihak ketiga (`intervaltree`) pada lingkungan proyek.
- Kode detektor hanya ~20 baris, mudah diaudit, dan konsisten memakai aturan interval setengah terbuka (`x.jam_selesai > j.jam_mulai`).
- Mudah diverifikasi secara matematis dan otomatis melalui *differential testing*.

**Negatif / Trade-off:**
- Tidak mendukung query rentang dinamis berfrekuensi tinggi (mis. `10^4+` query per detik terhadap koleksi interval yang berubah terus-menerus di memori).

---

## 5. Kapan Keputusan Ini Ditinjau Ulang (*Revisit Triggers*)

Keputusan ini akan ditinjau ulang dan beralih ke **Interval Tree** apabila salah satu kondisi berikut terpenuhi:
1. Modul berkembang menjadi **sistem peminjaman ruangan multi-tahun** dengan puluhan ribu slot aktif yang sering di-query berulang kali di memori.
2. Pada Minggu 8+ dibangun **CSP Solver / Auto-Scheduler** di memori yang mengevaluasi `10^4+` kandidat jadwal per detik sehingga pemindaian linear/sort-sweep menjadi *bottleneck* terukur di profiler.
