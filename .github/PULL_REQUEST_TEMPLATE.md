## Deskripsi Pull Request

- **Fitur:** <!-- contoh: Implementasi Modul PMB (Approve, NIM Generator, Status, Stats & Testing) -->
- **Isu yang Diselesaikan:** Closes #<!-- nomor-isu -->

---

## Penggunaan AI

- **Apa yang dibantu AI:**
  <!-- jelaskan bagian kode/skema/tes yang dibantu AI dan apa saja yang direvisi manual -->
- **3 Prompt Terbaik yang Dipakai:**
  1. `...`
  2. `...`
  3. `...`
- **Tautan AI Usage Log:** `prompts/ai-usage-log.md`

---

## Risiko & Limitasi (Jujur)

- [ ] <!-- contoh: Pengujian otomatis menggunakan SQLite in-memory sehingga perilaku row-level lock (`SELECT ... FOR UPDATE`) pada MySQL InnoDB belum diuji di bawah beban konkurensi nyata. -->
- [ ] <!-- contoh: Batas maksimal 9.999 pendaftar per prodi per tahun sesuai format 4 digit running number. -->

---

## Cara Uji

```bash
# 1. Jalankan migrasi database & uji rollback
alembic upgrade head
alembic downgrade -1
alembic upgrade head

# 2. Isi data master (Program Studi & Jalur Masuk)
python -m app.seed

# 3. Jalankan seluruh unit & integration tests + coverage
pytest -v --cov=app --cov-report=term-missing --cov-fail-under=80
```

---

## Screenshot / Log Hasil Uji

<!-- Tempelkan output pytest coverage, tangkapan layar Swagger UI (/docs), atau log Alembic di sini -->
