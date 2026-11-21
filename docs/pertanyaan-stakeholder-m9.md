# Pertanyaan Tertulis ke Stakeholder — Modul Nilai & Transkrip (Minggu 9)

**Kepada**: Dosen Pengampu Mata Kuliah / Bagian Akademik SEVIMA-Mini  
**Perihal**: Klarifikasi Kontradiksi Spesifikasi Batas Kelulusan Mata Kuliah (`≥ D (2.0)`)  
**Status**: `OPEN QUESTION` (Menunggu konfirmasi tertulis)

---

## 1. Kontradiksi yang Ditemukan pada Dokumen Tugas

Pada dokumen spesifikasi **Minggu 9–10: Modul Nilai & Transkrip**, bagian **4. Business Rules** tertulis:

> *"Lulus MK jika nilai ≥ D (2.0)"*

Namun berdasarkan tabel `skala_nilai` yang digunakan sejak Minggu 5:

| Huruf | Bobot |
| :---: | :---: |
| A | `4.00` |
| B | `3.00` |
| C | `2.00` |
| **D** | **`1.00`** |
| E | `0.00` |

Terdapat kontradiksi internal: huruf **D** bernilai **`1.00`**, sedangkan bobot **`2.00`** adalah huruf **C**.

## 2. Dampak Numerik terhadap Perhitungan IPK

Sebagai ilustrasi menggunakan data dummy **Rina (NIM `2025001`)**:
- Semester `20241`: Kalkulus 1 (3 SKS, **E**), Algoritma (4 SKS, **A**), Bahasa Inggris (2 SKS, **B**)
- Semester `20242`: Kalkulus 1 ulang (3 SKS, **B**), Struktur Data (3 SKS, **C**), Basis Data (3 SKS, **D**)

| Tafsiran Spesifikasi | Huruf Lulus | Rumus IPK Rina | IPK Rina |
| :--- | :---: | :---: | :---: |
| Angka `2.0` benar → **minimal C** | A, B, C | `37 / 12` | **`3.08`** |
| Huruf `D` benar → **minimal D** | A, B, C, D | `40 / 15` | **`2.67`** |

Perbedaan tafsiran ini menghasilkan **selisih `0.41` poin** pada IPK, yang dapat memengaruhi predikat kelulusan (Minggu 10) dan kelayakan beasiswa.

## 3. Pertanyaan untuk Stakeholder

1. **Batas lulus MK**: Apakah mahasiswa dinyatakan lulus mata kuliah pada nilai **minimal D (`1.00`)** atau **minimal C (`2.00`)**?
2. **Konsistensi dengan prasyarat (Minggu 5)**: Apakah batas kelulusan untuk perhitungan IPK ini **sama** dengan batas lulus prasyarat pengambilan MK pada modul KRS (Minggu 5, `bobot >= 2.0`)?

## 4. Asumsi Sementara & Kesiapan Perubahan

- Sambil menunggu konfirmasi tertulis, sistem menerapkan asumsi sementara **minimal C (`2.00`)** agar konsisten dengan modul prasyarat Minggu 5 (tercatat di `docs/ADR-005-modul-nilai-dan-ipk.md`).
- Karena aturan kelulusan disimpan sebagai **data** pada kolom `skala_nilai.lulus` (bukan di-*hardcode* pada logika Python), apabila stakeholder memutuskan batas lulus adalah **D (`1.00`)**, penyesuaian cukup dilakukan dengan mengubah **1 baris data**:
  ```sql
  UPDATE skala_nilai SET lulus = TRUE WHERE huruf = 'D';
  ```
  tanpa perlu mengubah satu baris kode pun pada domain perhitungan IPK.
