"""Seed data awal realistis untuk demo & pengujian Modul Keuangan (SPP)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import DATA_DIR
from app.models import (
    Billing,
    BillingStatus,
    Mahasiswa,
    Payment,
    PaymentMethod,
    PaymentSource,
    PaymentTxStatus,
)
from app.services.ai_report_service import export_live_payment_csv
from app.services.billing_service import apply_overdue_and_penalties, generate_billing, process_payment


PAYMENT_METHODS_SEED = [
    ("VA_BCA", "Virtual Account BCA", "gateway", 0),
    ("VA_BNI", "Virtual Account BNI", "gateway", 0),
    ("VA_MANDIRI", "Virtual Account Mandiri", "gateway", 0),
    ("QRIS", "QRIS Kampus", "gateway", 0),
    ("TRANSFER_MANUAL", "Transfer Bank Manual", "manual", 0),
    ("CASH_LOKET", "Loket Keuangan Kampus", "manual", 0),
]

MAHASISWA_SEED = [
    # Teknik (SPP Rp 5.000.000) - 12 aktif
    ("2401001", "Ahmad Fauzan Pratama", "ahmad.fauzan@student.kampus.ac.id", "Teknik", 2024, True),
    ("2401002", "Siti Nurhaliza", "siti.nurhaliza@student.kampus.ac.id", "Teknik", 2024, True),
    ("2401003", "Budi Santoso", "budi.santoso@student.kampus.ac.id", "Teknik", 2024, True),
    ("2401004", "Dewi Kartika Sari", "dewi.kartika@student.kampus.ac.id", "Teknik", 2024, True),
    ("2401005", "Rizky Ramadhan", "rizky.ramadhan@student.kampus.ac.id", "Teknik", 2024, True),
    ("2401006", "Nadia Kusuma", "nadia.kusuma@student.kampus.ac.id", "Teknik", 2024, True),
    ("2401007", "Dimas Aditya Putra", "dimas.aditya@student.kampus.ac.id", "Teknik", 2023, True),
    ("2401008", "Putri Rahmawati", "putri.rahmawati@student.kampus.ac.id", "Teknik", 2023, True),
    ("2401009", "Fajar Nugroho", "fajar.nugroho@student.kampus.ac.id", "Teknik", 2023, True),
    ("2401010", "Rina Wulandari", "rina.wulandari@student.kampus.ac.id", "Teknik", 2023, True),
    ("2401011", "Galih Permana", "galih.permana@student.kampus.ac.id", "Teknik", 2022, True),
    ("2401012", "Hana Puspita", "hana.puspita@student.kampus.ac.id", "Teknik", 2022, True),
    # Ekonomi (SPP Rp 4.000.000) - 11 aktif + 1 cuti (tidak aktif)
    ("2402001", "Arif Hidayat", "arif.hidayat@student.kampus.ac.id", "Ekonomi", 2024, True),
    ("2402002", "Lestari Wijaya", "lestari.wijaya@student.kampus.ac.id", "Ekonomi", 2024, True),
    ("2402003", "Bagas Prakoso", "bagas.prakoso@student.kampus.ac.id", "Ekonomi", 2024, True),
    ("2402004", "Ayu Melinda", "ayu.melinda@student.kampus.ac.id", "Ekonomi", 2024, True),
    ("2402005", "Yoga Mahendra", "yoga.mahendra@student.kampus.ac.id", "Ekonomi", 2023, True),
    ("2402006", "Intan Permatasari", "intan.permata@student.kampus.ac.id", "Ekonomi", 2023, True),
    ("2402007", "Reza Oktavian", "reza.oktavian@student.kampus.ac.id", "Ekonomi", 2023, True),
    ("2402008", "Clara Febrianti", "clara.febrianti@student.kampus.ac.id", "Ekonomi", 2023, True),
    ("2402009", "Ilham Saputra", "ilham.saputra@student.kampus.ac.id", "Ekonomi", 2022, True),
    ("2402010", "Tiara Anggraini", "tiara.anggraini@student.kampus.ac.id", "Ekonomi", 2022, True),
    ("2402011", "Kevin Gunawan", "kevin.gunawan@student.kampus.ac.id", "Ekonomi", 2022, True),
    ("2402012", "Naufal Cuti Akademik", "naufal.cuti@student.kampus.ac.id", "Ekonomi", 2022, False),
]


def _month_date(today: date, months_ago: int, day: int = 10) -> datetime:
    year = today.year
    month = today.month - months_ago
    while month <= 0:
        month += 12
        year -= 1
    safe_day = min(day, 28)
    return datetime(year, month, safe_day, 10, 30, 0)


def seed_database(db: Session, *, refresh_sample_csv: bool = True) -> bool:
    """Mengisi data awal jika database masih kosong. Mengembalikan True bila seeding dijalankan."""
    existing_pm = db.execute(select(func.count(PaymentMethod.id))).scalar_one()
    if existing_pm == 0:
        for code, name, channel_type, fee in PAYMENT_METHODS_SEED:
            db.add(PaymentMethod(code=code, name=name, channel_type=channel_type, admin_fee=fee))
        db.commit()

    existing_students = db.execute(select(func.count(Mahasiswa.id))).scalar_one()
    if existing_students > 0:
        return False

    for nim, nama, email, prodi, angkatan, aktif in MAHASISWA_SEED:
        db.add(
            Mahasiswa(
                nim=nim,
                nama=nama,
                email=email,
                program_studi=prodi,
                angkatan=angkatan,
                status_aktif=aktif,
            )
        )
    db.commit()

    today = date.today()
    # Semester sebelumnya (untuk histori grafik bulanan multi-bulan)
    prev_sem_start = (today - timedelta(days=150)).replace(day=1)
    generate_billing(db, semester="2025/2026-Genap", semester_start=prev_sem_start)

    # Lunasi mayoritas semester sebelumnya (sisakan 2 mahasiswa menunggak lama untuk realistis)
    prev_billings = (
        db.execute(select(Billing).where(Billing.semester == "2025/2026-Genap").order_by(Billing.id))
        .scalars()
        .all()
    )
    for idx, b in enumerate(prev_billings):
        if idx < len(prev_billings) - 2:
            months_back = 4 if idx % 3 == 0 else (3 if idx % 3 == 1 else 2)
            method = ["VA_BCA", "VA_BNI", "QRIS", "TRANSFER_MANUAL"][idx % 4]
            source = PaymentSource.WEBHOOK.value if method != "TRANSFER_MANUAL" else PaymentSource.MANUAL.value
            process_payment(
                db,
                billing_id=b.id,
                amount=b.total_amount,
                method=method,
                transaction_id=f"HIST-{b.billing_code}",
                source=source,
                paid_at=_month_date(today, months_back, day=5 + (idx % 18)),
                notes="Pembayaran historis semester sebelumnya",
            )

    # Semester berjalan: 2026/2027-Ganjil (mulai ~85 hari lalu agar overdue > 2 bulan terlihat jelas)
    curr_sem_start = today - timedelta(days=85)
    generate_billing(db, semester="2026/2027-Ganjil", semester_start=curr_sem_start)

    curr_billings = (
        db.execute(
            select(Billing)
            .join(Mahasiswa)
            .where(Billing.semester == "2026/2027-Ganjil")
            .order_by(Mahasiswa.nim)
        )
        .scalars()
        .all()
    )

    by_nim = {b.mahasiswa.nim: b for b in curr_billings}

    # 1. Mahasiswa PAID lunas bulan lalu & bulan ini (termasuk revenue bulan ini)
    paid_configs = [
        ("2401001", "VA_BCA", PaymentSource.WEBHOOK.value, 0, min(today.day, 5)),
        ("2401002", "VA_BNI", PaymentSource.WEBHOOK.value, 0, min(today.day, 9)),
        ("2401003", "QRIS", PaymentSource.WEBHOOK.value, 0, min(today.day, 14)),
        ("2401004", "VA_MANDIRI", PaymentSource.WEBHOOK.value, 1, 12),
        ("2401005", "TRANSFER_MANUAL", PaymentSource.MANUAL.value, 1, 18),
        ("2402001", "VA_BCA", PaymentSource.WEBHOOK.value, 0, min(today.day, 4)),
        ("2402002", "QRIS", PaymentSource.WEBHOOK.value, 0, min(today.day, 11)),
        ("2402003", "VA_BNI", PaymentSource.WEBHOOK.value, 0, min(today.day, 16)),
        ("2402004", "CASH_LOKET", PaymentSource.MANUAL.value, 1, 8),
        ("2402005", "VA_MANDIRI", PaymentSource.WEBHOOK.value, 1, 20),
        ("2402006", "VA_BCA", PaymentSource.WEBHOOK.value, 2, 14),
    ]
    for nim, method, source, months_ago, day_num in paid_configs:
        b = by_nim[nim]
        process_payment(
            db,
            billing_id=b.id,
            amount=b.total_amount,
            method=method,
            transaction_id=f"TRX-{b.billing_code}",
            source=source,
            paid_at=_month_date(today, months_ago, day=max(1, day_num)),
            notes="Pelunasan SPP semester berjalan",
        )

    # 2. Mahasiswa PARTIAL (cicil sebagian bulan ini, due_date masih aktif agar status tetap 'partial')
    partial_configs = [
        ("2401006", 2_500_000, "TRANSFER_MANUAL"),
        ("2401007", 2_000_000, "VA_BCA"),
        ("2402007", 1_500_000, "CASH_LOKET"),
    ]
    for nim, partial_amt, method in partial_configs:
        b = by_nim[nim]
        b.due_date = today + timedelta(days=5)
        db.commit()
        process_payment(
            db,
            billing_id=b.id,
            amount=partial_amt,
            method=method,
            transaction_id=f"PART-{b.billing_code}",
            source=PaymentSource.MANUAL.value,
            paid_at=_month_date(today, 0, day=max(1, min(today.day, 12))),
            notes="Cicilan tahap 1 SPP",
        )

    # 3. Mahasiswa UNPAID (jatuh tempo 2-7 hari lagi -> cocok untuk test webhook & reminder H-3!)
    for idx, nim in enumerate(["2401008", "2401009", "2402008"]):
        b = by_nim[nim]
        b.due_date = today + timedelta(days=2 + idx * 2)
    db.commit()

    # 4. Sisa mahasiswa (2401010, 2401011, 2401012, 2402009, 2402010, 2402011) tetap due_date >2 bulan lalu
    # Jalankan kalkulasi overdue & denda keterlambatan otomatis (tanpa spam email pada startup pertama)
    apply_overdue_and_penalties(db, as_of_date=today, send_reminders=False)

    # Ekspor sample CSV ke data/payment_data.csv agar konsisten untuk pengujian Deliverable 5
    if refresh_sample_csv:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        csv_path = DATA_DIR / "payment_data.csv"
        if not csv_path.exists():
            csv_path.write_text(export_live_payment_csv(db), encoding="utf-8")

    return True
