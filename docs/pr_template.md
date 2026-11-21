# Pull Request Template — Materi 4 Minggu 8 (SEVIMA-Mini)

## Ringkasan Perubahan
- Implementasi Observer Pattern (`ScheduleSubject`, `StudentObserver`, `LecturerObserver`, `AdminObserver`) + 3 kanal simulasi log (`EMAIL`, `SMS`, `PUSH`) dengan `Protocol` & kunci idempotensi.
- Implementasi Transactional Outbox (`Outbox` + `OutboxDispatcher`) dengan pengiriman pasca-`commit`, `skip_locked=True`, dan isolasi `try/except` per observer.
- Integrasi KRS (`KRSInvalidator`, `Actor.SISTEM`, 2 transisi baru ke `REVISION`, update test parametrize 48 kombinasi).
- AI-Powered Rescheduling (`hitung_slot_tersedia`, `LLMClient`, `saring_saran` 4 saringan) + Conflict Resolver UI (RBAC admin & prinsip satu pintu).
- Ekspor kalender iCalendar (`.ics`) RFC 5545 (`CRLF`, `TZID=Asia/Jakarta`, `UNTIL` UTC, `UID` stabil, `SEQUENCE` inkremental).

## Checklist Akhir Minggu 8
- [x] `ScheduleSubject` + 3 observer (`Student`, `Lecturer`, `Admin`) + kanal `EMAIL`/`SMS`/`PUSH` (log)
- [x] `Outbox` + `OutboxDispatcher` berjalan **setelah `commit`**
- [x] `KRSInvalidator` + transisi `Actor.SISTEM` + test parametrize 48 kombinasi (6 sah, 42 ilegal)
- [x] Prompt Step 3 + `saring_saran` (4 saringan) + Conflict Resolver UI (`require_admin` & satu pintu)
- [x] UML Sequence Diagram jujur sesuai kode di `docs/sequence_observer.md` (`COMMIT` di atas `notify`)
- [x] Ekspor kalender `.ics` (`GET /api/mahasiswa/{nim}/jadwal.ics`)
- [x] 4+ test utama lulus (`pytest`) tanpa memanggil API LLM sungguhan (`FakeLLM`)
- [x] AI Log dengan kerangka OPAR di `docs/ai_log_opar.md`

## Bukti Pengujian
```bash
pytest -v
python demo.py
```
