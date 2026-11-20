# Pull Request Template — Modul KRS (Materi 3: Minggu 5–6)

## Ringkasan Fitur
- Implementasi skema database Modul KRS (`matakuliah`, `krs`, `krs_detail`, `prerequisite`, `riwayat_nilai`, `log_krs`, `notifikasi`) beserta composite index optimasi.
- Implementasi pola **Chain of Responsibility** untuk validasi SKS (≤ 24), prasyarat (nilai ≥ C semester sebelumnya), bentrok jadwal, dan anti double enrollment.
- Implementasi **State Machine KRS** (`DRAFT → SUBMITTED → APPROVED / REVISION → SUBMITTED`) dengan enkapsulasi satu pintu `KRS.transition()`.
- Implementasi **Otorisasi 2 Lapis** (peran + kepemilikan `dosen_pa_id`), **Transaksi ACID**, serta **Concurrency Control** (`with_for_update()` + `version_id_col`).
- Implementasi **Unit, Integration, API, Exhaustive State Machine (32 kombinasi), & Property-Based Testing (Hypothesis 1000 contoh)**.
- *(Opsional +10%)* Implementasi **KRS Recommendation AI** berbasis CSP Backtracking dan Function-Calling LLM dengan guardrail `validate_krs()`.

## Isu Terkait
- Materi 3 — Minggu 5–6: Modul KRS (Kartu Rencana Studi) SEVIMA-Mini.

## Apa yang Dibantu AI
- Penyusunan boilerplate model SQLAlchemy, struktur Chain of Responsibility, query SQL prasyarat dengan `NOT EXISTS`, serta kerangka awal test Hypothesis & CSP backtracking.
- Revisi manual diterapkan pada: pengecekan kepemilikan `dosen_pa_id`, penolakan KRS kosong saat submit, `sentuh_perubahan()` untuk kenaikan `version` saat detail berubah, penulisan ulang property test agar menguji validator nyata + assert kedua + oracle independen, serta hardcode tabel sah pada test state machine.

## 3 Prompt Terbaik
1. *"Implementasikan Chain of Responsibility untuk validasi KRS (SKSValidator, PrerequisiteValidator, ConflictValidator, DuplicateValidator) yang mengembalikan ValidationResult(ok, message) dan berhenti di kegagalan pertama."*
2. *"Gunakan tabel transisi `dict[tuple[KRSStatus, Actor], set[KRSStatus]]` dengan satu pintu `transition()`, otorisasi 2 lapis cek `krs.dosen_pa_id`, tolak KRS kosong, bungkus approve/revise dalam satu transaksi ACID dengan `with_for_update()` dan `version_id_col`."*
3. *"Tulis Hypothesis property-based test 1000 contoh in-memory tanpa DB untuk menguji `SKSValidator` (total ≤ 24 dan penolakan beralasan) dan `ConflictValidator` (dengan oracle slot jam terpisah)."*

## Risiko & Limitasi (Disampaikan Secara Jujur)
1. **Identitas `dosen_pa_id` masih dikirim lewat request body** (`POST /api/krs/{nim}/approve` dan `/revise`) karena modul autentikasi/login belum diimplementasikan. Idealnya identitas dosen diambil dari token JWT/sesi login agar tidak dapat dipalsukan.
2. **Pengujian `SELECT ... FOR UPDATE` pada SQLite**: Suite test otomatis berjalan di SQLite in-memory yang mengabaikan klausa `FOR UPDATE`. Perilaku *pessimistic row locking* secara paralel perlu diuji manual pada MySQL/PostgreSQL.
3. **Notifikasi belum dikirim secara real-time**: Baris notifikasi baru dicatat di tabel `notifikasi` di dalam transaksi (sengaja tidak mengirim email di dalam transaksi agar tetap atomik); mekanisme pengiriman setelah commit akan dihubungkan lewat *Observer Pattern* pada Minggu 7–8.

## Cara Uji
```bash
pip install -r requirements.txt
pytest -v --cov=app --cov-report=term-missing
```

## Log & Dokumen Terkait
- AI Log + OPAR: `prompts/ai-usage-log.md`
- ADR State Machine: `docs/ADR-001-state-machine.md`
- Skema & Query SQL: `sql/schema.sql`
