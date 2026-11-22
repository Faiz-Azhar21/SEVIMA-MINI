-- ============================================================================
-- MINGGU 11: Modul Keuangan (SPP) - Payment Schema (Deliverable 1 - 25%)
-- Kompatibel dengan SQLite & PostgreSQL
-- ============================================================================

-- 1. Tabel Pendukung: Mahasiswa
CREATE TABLE IF NOT EXISTS mahasiswa (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nim             VARCHAR(20) NOT NULL UNIQUE,
    nama            VARCHAR(120) NOT NULL,
    email           VARCHAR(120) NOT NULL UNIQUE,
    program_studi   VARCHAR(80) NOT NULL,
    angkatan        INTEGER NOT NULL DEFAULT 2024,
    status_aktif    BOOLEAN NOT NULL DEFAULT 1,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 2. Tabel Utama: Payment Method
CREATE TABLE IF NOT EXISTS payment_method (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            VARCHAR(40) NOT NULL UNIQUE,
    name            VARCHAR(100) NOT NULL,
    channel_type    VARCHAR(20) NOT NULL CHECK (channel_type IN ('gateway', 'manual')),
    admin_fee       INTEGER NOT NULL DEFAULT 0 CHECK (admin_fee >= 0),
    is_active       BOOLEAN NOT NULL DEFAULT 1,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 3. Tabel Utama: Billing (Tagihan SPP per Semester)
CREATE TABLE IF NOT EXISTS billing (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    billing_code    VARCHAR(50) NOT NULL UNIQUE,
    mahasiswa_id    INTEGER NOT NULL,
    semester        VARCHAR(30) NOT NULL,
    semester_start  DATE NOT NULL,
    base_amount     INTEGER NOT NULL CHECK (base_amount > 0),
    penalty_amount  INTEGER NOT NULL DEFAULT 0 CHECK (penalty_amount >= 0),
    total_amount    INTEGER NOT NULL CHECK (total_amount > 0),
    paid_amount     INTEGER NOT NULL DEFAULT 0 CHECK (paid_amount >= 0),
    due_date        DATE NOT NULL,
    status          VARCHAR(15) NOT NULL DEFAULT 'unpaid'
                    CHECK (status IN ('unpaid', 'partial', 'paid', 'overdue')),
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (mahasiswa_id) REFERENCES mahasiswa(id) ON DELETE RESTRICT,
    UNIQUE (mahasiswa_id, semester)
);

-- 4. Tabel Utama: Payment (Riwayat Pembayaran Manual / Auto via Webhook)
CREATE TABLE IF NOT EXISTS payment (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    billing_id          INTEGER NOT NULL,
    payment_method_id   INTEGER NOT NULL,
    transaction_id      VARCHAR(80) NOT NULL UNIQUE,
    amount              INTEGER NOT NULL CHECK (amount > 0),
    source              VARCHAR(20) NOT NULL DEFAULT 'manual'
                        CHECK (source IN ('manual', 'webhook')),
    status              VARCHAR(20) NOT NULL DEFAULT 'success'
                        CHECK (status IN ('success', 'pending', 'failed')),
    paid_at             DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    notes               TEXT,
    raw_payload         TEXT,
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (billing_id) REFERENCES billing(id) ON DELETE RESTRICT,
    FOREIGN KEY (payment_method_id) REFERENCES payment_method(id) ON DELETE RESTRICT
);

-- 5. Tabel Pendukung: KRS Enrollment (Verifikasi Block KRS jika ada tunggakan)
CREATE TABLE IF NOT EXISTS krs_enrollment (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    mahasiswa_id    INTEGER NOT NULL,
    semester        VARCHAR(30) NOT NULL,
    mata_kuliah     TEXT NOT NULL,
    total_sks       INTEGER NOT NULL CHECK (total_sks > 0 AND total_sks <= 24),
    status          VARCHAR(20) NOT NULL DEFAULT 'approved',
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (mahasiswa_id) REFERENCES mahasiswa(id) ON DELETE RESTRICT,
    UNIQUE (mahasiswa_id, semester)
);

-- 6. Tabel Pendukung: Email Log (Audit Receipt Pembayaran & Reminder Otomatis)
CREATE TABLE IF NOT EXISTS email_log (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    mahasiswa_id        INTEGER,
    billing_id          INTEGER,
    recipient_email     VARCHAR(120) NOT NULL,
    email_type          VARCHAR(20) NOT NULL CHECK (email_type IN ('receipt', 'reminder')),
    subject             VARCHAR(200) NOT NULL,
    body                TEXT NOT NULL,
    delivery_status     VARCHAR(20) NOT NULL DEFAULT 'simulated',
    receipt_file_path   VARCHAR(255),
    sent_at             DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (mahasiswa_id) REFERENCES mahasiswa(id) ON DELETE SET NULL,
    FOREIGN KEY (billing_id) REFERENCES billing(id) ON DELETE SET NULL
);

-- Indexes untuk performa query dashboard & pencarian
CREATE INDEX IF NOT EXISTS idx_billing_mahasiswa ON billing(mahasiswa_id);
CREATE INDEX IF NOT EXISTS idx_billing_status ON billing(status);
CREATE INDEX IF NOT EXISTS idx_billing_semester ON billing(semester);
CREATE INDEX IF NOT EXISTS idx_billing_due_date ON billing(due_date);
CREATE INDEX IF NOT EXISTS idx_payment_billing ON payment(billing_id);
CREATE INDEX IF NOT EXISTS idx_payment_paid_at ON payment(paid_at);
CREATE INDEX IF NOT EXISTS idx_mahasiswa_prodi ON mahasiswa(program_studi);
