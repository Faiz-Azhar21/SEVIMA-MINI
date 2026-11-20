-- =============================================================================
-- SEVIMA-Mini: Modul KRS (Kartu Rencana Studi) — Minggu 5-6
-- Database Schema DDL + Indexes + Query Prasyarat
-- Kompatibel dengan PostgreSQL / MySQL 8+ / SQLite 3
-- =============================================================================

-- 1. Tabel Matakuliah
CREATE TABLE IF NOT EXISTS matakuliah (
    kode_mk       VARCHAR(20)  PRIMARY KEY,
    kode_induk    VARCHAR(20)  NOT NULL,          -- Kode MK induk (sama antar kelas paralel, mis. IF201)
    kelas         VARCHAR(10)  NOT NULL DEFAULT 'A',
    nama          VARCHAR(120) NOT NULL,
    sks           INTEGER      NOT NULL CHECK (sks BETWEEN 1 AND 6),
    hari          INTEGER      NOT NULL CHECK (hari BETWEEN 1 AND 6), -- 1=Senin .. 6=Sabtu
    jam_mulai     TIME         NOT NULL,
    jam_selesai   TIME         NOT NULL,
    jenis         VARCHAR(10)  NOT NULL DEFAULT 'WAJIB' CHECK (jenis IN ('WAJIB', 'PILIHAN')),
    CHECK (jam_selesai > jam_mulai)
);

-- 2. Tabel Prerequisite (Relasi prasyarat antar mata kuliah)
CREATE TABLE IF NOT EXISTS prerequisite (
    kode_mk            VARCHAR(20) NOT NULL,
    prasyarat_kode_mk  VARCHAR(20) NOT NULL,
    nilai_minimal      VARCHAR(2)  NOT NULL DEFAULT 'C',
    PRIMARY KEY (kode_mk, prasyarat_kode_mk),
    FOREIGN KEY (kode_mk)           REFERENCES matakuliah(kode_mk) ON DELETE CASCADE,
    FOREIGN KEY (prasyarat_kode_mk) REFERENCES matakuliah(kode_mk) ON DELETE CASCADE,
    CHECK (kode_mk <> prasyarat_kode_mk)
);

-- 3. Tabel Riwayat Nilai (Nilai semester sebelumnya untuk validasi prasyarat >= C)
CREATE TABLE IF NOT EXISTS riwayat_nilai (
    id           INTEGER      PRIMARY KEY AUTOINCREMENT,
    nim          VARCHAR(20)  NOT NULL,
    kode_mk      VARCHAR(20)  NOT NULL,
    semester     INTEGER      NOT NULL CHECK (semester >= 1),
    nilai_huruf  VARCHAR(2)   NOT NULL CHECK (nilai_huruf IN ('A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'D', 'E')),
    FOREIGN KEY (kode_mk) REFERENCES matakuliah(kode_mk) ON DELETE RESTRICT
);

-- 4. Tabel KRS (Header KRS per mahasiswa per semester)
-- Menggunakan 1 kolom status (Enum) bukan kolom boolean terpisah,
-- serta kolom version untuk Optimistic Locking.
CREATE TABLE IF NOT EXISTS krs (
    id              INTEGER      PRIMARY KEY AUTOINCREMENT,
    nim             VARCHAR(20)  NOT NULL,
    semester        INTEGER      NOT NULL CHECK (semester >= 1),
    dosen_pa_id     INTEGER      NOT NULL,
    status          VARCHAR(16)  NOT NULL DEFAULT 'DRAFT'
                    CHECK (status IN ('DRAFT', 'SUBMITTED', 'APPROVED', 'REVISION')),
    submitted_at    TIMESTAMP    NULL,
    approved_at     TIMESTAMP    NULL,
    catatan_revisi  TEXT         NULL,
    diubah_pada     TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version         INTEGER      NOT NULL DEFAULT 1,
    UNIQUE (nim, semester)
);

-- 5. Tabel KRS Detail (Many-to-many antara KRS mahasiswa dan Matakuliah)
CREATE TABLE IF NOT EXISTS krs_detail (
    id        INTEGER     PRIMARY KEY AUTOINCREMENT,
    krs_id    INTEGER     NOT NULL,
    kode_mk   VARCHAR(20) NOT NULL,
    FOREIGN KEY (krs_id)  REFERENCES krs(id)             ON DELETE CASCADE,
    FOREIGN KEY (kode_mk) REFERENCES matakuliah(kode_mk) ON DELETE RESTRICT,
    UNIQUE (krs_id, kode_mk)
);

-- 6. Tabel Log KRS (Audit trail transaksi approval/revisi/submit)
CREATE TABLE IF NOT EXISTS log_krs (
    id          INTEGER      PRIMARY KEY AUTOINCREMENT,
    krs_id      INTEGER      NOT NULL,
    aksi        VARCHAR(32)  NOT NULL,
    aktor       VARCHAR(64)  NOT NULL,
    catatan     TEXT         NULL,
    created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (krs_id) REFERENCES krs(id) ON DELETE CASCADE
);

-- 7. Tabel Notifikasi (Disimpan sebagai baris DB dalam transaksi; dikirim via Observer di Minggu 7-8)
CREATE TABLE IF NOT EXISTS notifikasi (
    id          INTEGER      PRIMARY KEY AUTOINCREMENT,
    nim         VARCHAR(20)  NOT NULL,
    pesan       TEXT         NOT NULL,
    terkirim    BOOLEAN      NOT NULL DEFAULT 0,
    created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- =============================================================================
-- INDEXES (Optimasi Query Prasyarat, Lookup KRS, dan Deteksi Bentrok)
-- =============================================================================
-- Covering index untuk mengambil semua prasyarat dari matakuliah X
CREATE INDEX IF NOT EXISTS idx_prerequisite_kode_mk
    ON prerequisite (kode_mk, prasyarat_kode_mk, nilai_minimal);

-- Covering index untuk pengecekan EXISTS nilai mahasiswa Y di semester sebelumnya
CREATE INDEX IF NOT EXISTS idx_riwayat_nilai_nim_mk_sem
    ON riwayat_nilai (nim, kode_mk, semester, nilai_huruf);

-- Index pencarian KRS berdasarkan nim & dosen_pa_id
CREATE INDEX IF NOT EXISTS idx_krs_nim_semester
    ON krs (nim, semester);
CREATE INDEX IF NOT EXISTS idx_krs_dosen_pa
    ON krs (dosen_pa_id, status);

-- Index lookup detail KRS dan kelas paralel matakuliah
CREATE INDEX IF NOT EXISTS idx_krs_detail_krs_id
    ON krs_detail (krs_id, kode_mk);
CREATE INDEX IF NOT EXISTS idx_matakuliah_kode_induk
    ON matakuliah (kode_induk);

-- =============================================================================
-- STEP 3: COMPLEX SQL QUERY FOR PREREQUISITE CHECK
-- Mengembalikan daftar prasyarat dari :kode_mk yang BELUM terpenuhi oleh :nim
-- (belum diambil atau nilai < C atau bukan dari semester sebelumnya).
-- =============================================================================
-- SELECT p.prasyarat_kode_mk AS kode_mk, m.nama AS nama
-- FROM prerequisite p
-- JOIN matakuliah m ON m.kode_mk = p.prasyarat_kode_mk
-- WHERE p.kode_mk = :kode_mk
--   AND NOT EXISTS (
--       SELECT 1
--       FROM riwayat_nilai rn
--       WHERE rn.nim = :nim
--         AND rn.kode_mk = p.prasyarat_kode_mk
--         AND rn.semester < :semester_sekarang
--         AND CASE rn.nilai_huruf
--               WHEN 'A'  THEN 4.0
--               WHEN 'A-' THEN 3.7
--               WHEN 'B+' THEN 3.3
--               WHEN 'B'  THEN 3.0
--               WHEN 'B-' THEN 2.7
--               WHEN 'C+' THEN 2.3
--               WHEN 'C'  THEN 2.0
--               WHEN 'D'  THEN 1.0
--               ELSE 0.0
--             END >= CASE COALESCE(p.nilai_minimal, 'C')
--               WHEN 'A'  THEN 4.0
--               WHEN 'A-' THEN 3.7
--               WHEN 'B+' THEN 3.3
--               WHEN 'B'  THEN 3.0
--               WHEN 'B-' THEN 2.7
--               WHEN 'C+' THEN 2.3
--               WHEN 'C'  THEN 2.0
--               WHEN 'D'  THEN 1.0
--               ELSE 0.0
--             END
--   )
-- ORDER BY p.prasyarat_kode_mk;
