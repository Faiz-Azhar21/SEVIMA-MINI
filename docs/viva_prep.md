# Panduan Persiapan Viva (Tanpa AI) & Demo Singkat Minggu 8

## 1. Dua Pertanyaan Wajib Viva

### Q1: Mengapa notifikasi harus dikirim *setelah `commit`* (lewat Transactional Outbox), bukan sebelum `commit`?
- Jika notifikasi dikirim sebelum `db.commit()`, lalu transaksi gagal dan di-**rollback** (misalnya karena *constraint error* atau koneksi DB putus), mahasiswa/dosen **sudah terlanjur menerima kabar perubahan jadwal yang tidak pernah terjadi**.
- Sebaliknya, jika `UPDATE jadwal`, invalidasi KRS, dan `INSERT outbox` ditulis dalam **satu transaksi yang sama**, keduanya bersifat **atomik**: kalau commit berhasil, janji notifikasi pasti tercatat; kalau gagal, keduanya hilang bersama.
- Setelah `commit` berhasil, `OutboxDispatcher` mengirim notifikasi. Jika server email/SMS mati, jadwal yang sudah sah **tidak ikut batal** — baris outbox tetap `PENDING` dan dicoba ulang sampai 5 kali, dengan **idempotency key** (`{event_id}:{penerima}:{channel}`) mencegah pesan ganda ke observer yang sebelumnya sudah sukses.

### Q2: Mengapa saran jadwal dari AI *harus divalidasi ulang* oleh kode kita?
- LLM bersifat probabilistik dan bisa **berhalusinasi**: membalas dengan teks di luar JSON, mengarang kode ruangan fiktif, memilih ruangan berkapasitas lebih kecil dari peserta, atau menyarankan slot yang bentrok dengan jadwal dosen/ruangan.
- Prinsip **"Never Trust, Always Validate"**: AI hanya memilih dan memberi alasan dari slot tersedia yang dihitung kode kita, lalu setiap jawabannya wajib melewati **4 saringan**:
  1. **Parsing JSON** (ekstrak `[`..`]`, rusak → `[]`).
  2. **Skema Pydantic** (`Saran`: hari 1–6, format jam valid; item rusak dibuang satu per satu).
  3. **Eksistensi & Kapasitas Ruangan** di database (`kapasitas >= max(kuota, terdaftar)`).
  4. **Deteksi Bentrok 3 Dimensi** (`detect_schedule_conflict` dengan jadwal calon ber-`id=-1`).
- Selain itu, saat admin menekan **Terapkan**, sistem tetap melewati **satu pintu `SchedulingService.update()`** agar bila admin lain keburu mengambil slot tersebut (*race condition*), server menolak dengan HTTP `409 Conflict`.

### Q3 (Bonus): Apa bedanya Observer Pattern dan Pub-Sub?
- **Observer**: Subject memegang daftar observer langsung, tanpa perantara, biasanya sinkron dalam 1 proses (`ScheduleSubject` di SEVIMA-Mini).
- **Pub-Sub**: Publisher hanya mengirim ke *topik* melalui *event bus/broker* (Redis, RabbitMQ, Kafka), biasanya asinkron dan lintas proses. Tabel `outbox` di proyek ini adalah langkah awal menuju Pub-Sub.

---

## 2. Alur Demo Singkat (1 Menit)
1. Jalankan `python demo.py` (atau jalankan server `uvicorn app.main:app --reload` lalu buka `http://127.0.0.1:8000/`).
2. Tunjukkan konflik awal (`room_conflict` Jadwal #12 & #15, `lecturer_conflict` Jadwal #17 & #21).
3. Klik **Saran AI #12** → tampil maksimal 3 saran tervalidasi → klik **Terapkan**.
4. Tunjukkan **3 bukti hasil**:
   - Tabel **Outbox** mencatat event `SCHEDULE_CHANGED` berstatus `SENT`.
   - **Log Notifikasi** mencatat pengiriman di 3 kanal: `EMAIL`, `SMS`, dan `PUSH` lengkap dengan `idempotency_key`.
   - Status KRS **Rina (`APPROVED`)** dan **Doni (`SUBMITTED`)** otomatis berubah ke **`REVISION`**, sedangkan **Siti (`DRAFT`)** tetap `DRAFT`.
5. Unduh `/api/mahasiswa/2301001/jadwal.ics` untuk menunjukkan `UID` stabil, `RRULE` mingguan (`UNTIL` UTC `Z`), pemisah `CRLF`, dan `SEQUENCE:1`.
