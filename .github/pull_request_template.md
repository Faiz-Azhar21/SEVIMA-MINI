## Ringkasan Fitur / Isu

- **Modul**: Materi 4 — Minggu 7 (Modul Jadwal & Ruangan, Bagian 1)
- **Deskripsi**:
  - [ ] Model SQLAlchemy 2.0 (`Ruangan`, `Dosen`, `Kelas`, `Jadwal`) + migrasi Alembic (`krs_detail.kelas_id`, pindah `hari/jam` dari `matakuliah`)
  - [ ] Algoritma deteksi bentrok 3D: `detect_naive` (`O(n^2)`) & `detect_schedule_conflict` (grouping + sort & sweep `O(n log n + k)`)
  - [ ] `SchedulingService` (`create`, `update`, `delete`, *capacity check* `max(kuota, terdaftar)`, *pessimistic row lock*)
  - [ ] API `/api/jadwal` (`POST`, `PUT`, `DELETE`, `GET /conflicts`) + exception handler polimorfik HTTP `409`
  - [ ] Seed data (`>=10` ruangan, `>=15` dosen, `>=40` jadwal + bentrok sengaja)
  - [ ] Test (`parametrize`, Hypothesis invariant & differential) + ADR Interval Tree + OPAR + AI Log

## Apa yang Dibantu AI

- Menyusun struktur awal model SQLAlchemy 2.0, skema Pydantic, detektor bentrok, dan test fixture.
- **Revisi manual yang dilakukan**:
  - Memastikan interval setengah terbuka (`<` / `>`, bukan `<=` / `>=`) untuk kuliah bersambung `09:40`.
  - Memastikan tipe waktu `datetime.time` (bukan `str`).
  - Menghapus tipe `'time_overlap'` (irisan waktu saja = normal).
  - Memakai `max(kelas.kuota, terdaftar)` pada *capacity check* awal semester.
  - Menempatkan `db.add(jadwal)` paling akhir untuk menghindari *autoflush* dan mengurutkan lock `Ruangan` → `Dosen`.

## Prompt Kunci

Lihat rincian lengkap prompt penutup celah bug di [prompts/ai-usage-log.md](prompts/ai-usage-log.md).

## Risiko & Limitasi

1. **Filter semester aktif belum diterapkan pada `_bentrok_di_db()` dan `list_conflicts()`**: Saat ini deteksi menganggap seluruh baris di tabel `jadwal` berada pada semester aktif yang sama. Jika data multi-semester disimpan bersamaan, query perlu di-join ke `kelas.semester`.
2. **Pembuktian konkurensi (`with_for_update()`) harus dijalankan di MySQL (InnoDB)**: SQLite mengabaikan row-level lock sehingga uji paralel dua admin pada SQLite tidak mencerminkan perilaku penguncian produksi.
3. **Generator Hypothesis menggunakan jam bulat**: Kasus batas menit (seperti `09:40`) tetap dijaga oleh *example-based tests* di `tests/test_conflict.py`.
4. **Interval Tree ditunda**: Terdokumentasi beserta hasil pengukuran benchmark di [docs/adr/001-tunda-interval-tree.md](docs/adr/001-tunda-interval-tree.md).

## Cara Uji

```bash
# 1. Jalankan migrasi & seed data
alembic upgrade head
python -m scripts.seed --reset

# 2. Jalankan seluruh suite pengujian & coverage
pytest --cov=app --cov-report=term-missing

# 3. Jalankan benchmark empiris (pendukung ADR)
python -m scripts.benchmark_conflict
```

## Referensi Log & Dokumentasi

- AI Usage Log: [prompts/ai-usage-log.md](prompts/ai-usage-log.md)
- Catatan OPAR: [docs/opar-minggu-7.md](docs/opar-minggu-7.md)
- ADR Interval Tree: [docs/adr/001-tunda-interval-tree.md](docs/adr/001-tunda-interval-tree.md)
