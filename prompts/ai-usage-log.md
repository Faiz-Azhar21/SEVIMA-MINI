# AI Usage Log — Minggu 7 (Modul Jadwal & Ruangan)

```text
Minggu     : 7 (Materi 4 — Bagian 1)
Fitur      : Model Jadwal & Ruangan, detect_schedule_conflict, SchedulingService, API /api/jadwal
Tujuan     : Menolak bentrok ruangan/dosen & kapasitas berlebih sebelum commit, serta melaporkan bentrok terlanjur ada
LLM/Tool   : Gemini (utama) & model pembanding (referensi audit bug klasik)
```

---

## 1. Prompt Kunci (Menutup 5 Celah Bug Klasik AI)

Prompt awal dari dokumen tugas (Step 1) diperketat dengan batasan spesifikasi berikut sebelum meminta implementasi:

> Implementasikan modul deteksi bentrok jadwal pada Python 3.12 + SQLAlchemy 2.0 untuk model `Ruangan`, `Dosen`, `Kelas`, dan `Jadwal`:
> 1. Interval bersifat **setengah terbuka** `[mulai, selesai)`: kuliah bersambung `08:00-09:40` dan `09:40-11:20` **TIDAK** dianggap bentrok (gunakan `<` / `>`, bukan `<=` / `>=`).
> 2. `jam_mulai` dan `jam_selesai` bertipe `datetime.time`, **BUKAN** `str` (validasi di Pydantic `JadwalIn` serta `CheckConstraint` di SQLAlchemy).
> 3. Cek kesamaan `hari` wajib dilakukan sebelum membandingkan jam.
> 4. Setiap pasangan jadwal yang bertumpuk dilaporkan **tepat sekali per tipe** dengan urutan ID kanonik (`tuple(sorted((a.id, b.id)))`).
> 5. Tipe konflik hanya `Literal["room_conflict", "lecturer_conflict"]` — **JANGAN** laporkan `'time_overlap'` karena irisan waktu pada ruangan dan dosen berbeda adalah kondisi normal.
> 6. Output berupa `@dataclass(frozen=True) class Conflict` agar *hashable* untuk `set`/`Counter`.
> 7. Sediakan dua versi: `detect_naive` (`itertools.combinations`) sebagai acuan dan `detect_schedule_conflict` (grouping + sort & sweep), plus *differential test* yang membuktikan keduanya menghasilkan `Counter` yang identik.

---

## 2. Kode AI Mentah & Revisi Manual yang Dilakukan

| No | Temuan / Celah pada Desain Awal atau Output AI | Revisi Manual yang Diterapkan | Penjaga Permanen di Test |
| :-: | :--- | :--- | :--- |
| 1 | Perbandingan interval memakai `<=` | Diganti menjadi `<` di `overlap()` dan `>` di *sweep* (`x.jam_selesai > j.jam_mulai`) | `test_detect_schedule_conflict_cases` (kasus `09:40`) & `test_post_kuliah_bersambung_0940_diizinkan_201` |
| 2 | Tipe jam disimpan/dibandingkan sebagai `str` | Memakai `datetime.time` pada model ORM, `JadwalSlot`, dan skema Pydantic `JadwalIn` | `test_perbandingan_waktu_jam_9_dan_jam_10` |
| 3 | Lupa memeriksa `a.hari == b.hari` | Ditambahkan syarat `a.hari == b.hari` di `overlap()` dan `(j.hari, ...)` di kunci grouping | `test_detect_schedule_conflict_cases` (kasus beda hari) |
| 4 | Loop ganda melaporkan `(A, B)` dan `(B, A)` | Memakai `itertools.combinations` (naif) dan `_pasangan()` yang mengurutkan ID kanonik | `test_urutan_input_terbalik_menghasilkan_conflict_kanonik` & `Counter` pada `test_sweep_sama_dengan_naif` |
| 5 | Tipe `'time_overlap'` ikut dilaporkan sebagai konflik | Dihapus dari `ConflictType`; dibatasi dengan `Literal["room_conflict", "lecturer_conflict"]` | `test_detect_schedule_conflict_cases` (ruang & dosen berbeda -> `set()`) |
| 6 | Capacity check hanya menghitung `terdaftar` (`KRSDetail`) sehingga lolos saat awal semester (`terdaftar = 0`) | Diubah menjadi `peserta = max(kelas.kuota, terdaftar)` | `test_post_kapasitas_awal_semester_kuota_melebihi_ruang_409` & `test_post_kapasitas_terdaftar_melebihi_ruang_409` |
| 7 | `db.add(jadwal)` dipanggil sebelum query `_bentrok_di_db` memicu *SQLAlchemy autoflush* | Memindahkan `db.add(jadwal)` paling akhir tepat sebelum `db.commit()` | `test_put_geser_15_menit_tidak_bentrok_dengan_diri_sendiri` |
| 8 | Global `@event.listens_for(Engine, "connect")` memblokir `batch_alter_table` Alembic di SQLite | Listener `PRAGMA foreign_keys=ON` dipasang khusus pada instance `engine` aplikasi dan fixture test | `test_alembic_migration_upgrade_dan_downgrade` |

---

## 3. Uji & Hasil

- **Unit & Example-Based Tests (`tests/test_conflict.py`)**: 10 test kasus (seluruh 5 bug klasik AI + constraint DB) — **LULUS**.
- **Property-Based & Differential Tests (`tests/test_conflict_property.py`)**: 2 properti Hypothesis (`max_examples=500` per properti = 1.000 skenario acak; pemeriksa independen slot per jam + `Counter(sweep) == Counter(naive)`) — **LULUS**.
- **API, Seed & Migration Integration Tests (`tests/test_scheduling_api.py`)**: 17 test (HTTP `201`, `200`, `204`, `404`, `409`, `422`, rollback saat PUT bentrok, seed data, migrasi Alembic `upgrade`/`downgrade`) — **LULUS**.
- **Benchmark Empiris (`scripts/benchmark_conflict.py`)**: Di `N = 600`, sweep berjalan dalam `1.040 ms` vs naif `10.024 ms` (9.6× lebih cepat, hasil 100% identik) → dicatat di `docs/adr/001-tunda-interval-tree.md`.
