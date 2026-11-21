# AI Usage Log — Kerangka OPAR (Materi 4 Minggu 8)

Catatan penggunaan AI dengan pendekatan **OPAR** (*Objective, Prompt, Audit/Assessment, Refinement*) selama membangun Modul Jadwal & Ruangan (Minggu 7–8) SEVIMA-Mini.

---

## Entri 1 — Implementasi Observer Pattern, Outbox, & Idempotency Key

- **Objective (Tujuan):** Memisahkan logika perubahan jadwal dari pengiriman notifikasi (mematuhi *Open-Closed Principle*), dengan 3 observer (`StudentObserver`, `LecturerObserver`, `AdminObserver`), 3 kanal simulasi log (`EMAIL`, `SMS`, `PUSH`), serta jaminan transaksi aman.
- **Prompt (diperkuat dari Step 2 PDF):**
  > Implementasikan Observer pattern (`ScheduleSubject`, `StudentObserver`, `LecturerObserver`, `AdminObserver`) dengan `ScheduleEvent` immutable (`frozen=True`), `Observer` & `Channel` berbasis `Protocol`, notifikasi HANYA setelah commit melalui tabel `Outbox` + `OutboxDispatcher`, tiap `observer.update()` dibungkus `try/except`, observer dirangkai sekali saat startup, dan tiap pengiriman memiliki kunci idempotensi `{event_id}:{penerima}:{channel}`.
- **Audit / Temuan Kritis terhadap Pola AI Standar:**
  1. Jika hanya memakai prompt Step 2 mentah, AI sering memanggil `notify()` sebelum `db.commit()` (risiko notifikasi palsu saat rollback).
  2. Loop `notify()` mentah berhenti bila satu observer melempar exception.
  3. Mendaftarkan observer di dalam route FastAPI memicu *memory leak* & pesan berlipat.
  4. Retry outbox tanpa `IdemStore` mengirim ulang pesan ke kanal yang sebelumnya sudah sukses.
- **Refinement & Verification:**
  - Memisahkan `Outbox` (ditulis dalam transaksi `_simpan()`) dan `OutboxDispatcher` (dijalankan setelah `commit()` dengan `with_for_update(skip_locked=True)` dan `MAX_ATTEMPTS = 5`).
  - Memilih `typing.Protocol` dibanding `ABC` agar `SpyObserver`, `RusakObserver`, dan kanal baru tidak terikat hierarki pewarisan.
  - Diverifikasi melalui `tests/test_jadwal_observer.py` (dedup `attach`, isolasi `RusakObserver`, uji rollback vs commit, dan uji retry + idempotensi).

---

## Entri 2 — Integrasi KRS (`KRSInvalidator` & Transisi State Machine)

- **Objective (Tujuan):** Mengembalikan KRS terdampak perubahan jadwal ke status `REVISION` tanpa melanggar state machine Minggu 6.
- **Prompt:**
  > Tambahkan `Actor.SISTEM` serta dua transisi resmi `(SUBMITTED, SISTEM) -> REVISION` dan `(APPROVED, SISTEM) -> REVISION` pada state machine KRS. Buat `KRSInvalidator` dengan row lock (`with_for_update()`) yang hanya menyentuh status `SUBMITTED`/`APPROVED` dan tidak melakukan `commit()` sendiri.
- **Audit / Temuan Kritis:**
  - Menulis `krs.status = KRSStatus.REVISION` langsung adalah jalan pintas berbahaya yang mem-bypass aturan domain.
  - Menambahkan 1 aktor baru mengubah dimensi matriks transisi dari Minggu 6 menjadi `4 × 4 × 3 = 48` kombinasi (6 sah, 42 ilegal).
- **Refinement & Verification:**
  - Semua perubahan status tetap melalui `krs.transition(KRSStatus.REVISION, Actor.SISTEM)`.
  - Diverifikasi dengan test parametrize 48 kombinasi di `tests/test_krs_transitions.py` dan integration test `test_update_invalidasi_krs`.

---

## Entri 3 — AI-Powered Rescheduling & 4 Saringan Validasi

- **Objective (Tujuan):** Memberikan hingga 3 saran jadwal alternatif untuk menyelesaikan konflik di Conflict Resolver UI tanpa pernah mempercayai output mentah LLM.
- **Prompt (Step 3):**
  > Hitung daftar *available slots* secara deterministik oleh kode memakai `detect_schedule_conflict`, bangun prompt JSON terstruktur, bungkus LLM di belakang `LLMClient(Protocol)`, dan terapkan 4 saringan (`parse_saran` JSON, Pydantic `Saran`, cek keberadaan & kapasitas ruangan di DB, serta simulasi `detect_schedule_conflict` dengan calon `id=-1`).
- **Audit / Temuan Kritis:**
  - LLM dapat membungkus JSON dengan teks pembuka/markdown, mengarang kode ruangan fiktif (`Z999`), memilih ruangan terlalu kecil, atau merekomendasikan slot bentrok.
  - Memanggil API LLM sungguhan di unit test menyebabkan test lambat, tidak deterministik, dan gagal di CI tanpa API key.
- **Refinement & Verification:**
  - Menerapkan `saring_saran()` dengan 4 lapisan validasi dan batas maksimum 3 saran.
  - Tombol **Terapkan** di UI wajib memanggil `SchedulingService.update()` yang sama (*prinsip satu pintu*) untuk mencegah *race condition* antar-admin (mengembalikan `409 Conflict` jika slot keburu terambil).
  - Diverifikasi deterministik memakai `FakeLLM` di `tests/test_jadwal_observer.py` dan uji *race condition* `409` di `tests/test_api_and_ical.py`.
