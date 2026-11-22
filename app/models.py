"""Deliverable 1: Payment Schema (ORM Models SQLAlchemy).

Tabel utama:
- payment_method
- billing (status: unpaid, partial, paid, overdue)
- payment

Tabel pendukung integrasi akademik & audit:
- mahasiswa
- krs_enrollment
- email_log
"""

from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class BillingStatus(str, enum.Enum):
    UNPAID = "unpaid"
    PARTIAL = "partial"
    PAID = "paid"
    OVERDUE = "overdue"


class PaymentSource(str, enum.Enum):
    MANUAL = "manual"
    WEBHOOK = "webhook"


class PaymentTxStatus(str, enum.Enum):
    SUCCESS = "success"
    PENDING = "pending"
    FAILED = "failed"


class Mahasiswa(Base):
    __tablename__ = "mahasiswa"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nim: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    nama: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    program_studi: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    angkatan: Mapped[int] = mapped_column(Integer, nullable=False, default=2024)
    status_aktif: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)

    billings: Mapped[list[Billing]] = relationship(back_populates="mahasiswa", cascade="all, delete-orphan")
    krs_enrollments: Mapped[list[KrsEnrollment]] = relationship(
        back_populates="mahasiswa", cascade="all, delete-orphan"
    )


class PaymentMethod(Base):
    __tablename__ = "payment_method"
    __table_args__ = (
        CheckConstraint("channel_type IN ('gateway', 'manual')", name="ck_payment_method_channel_type"),
        CheckConstraint("admin_fee >= 0", name="ck_payment_method_admin_fee"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    channel_type: Mapped[str] = mapped_column(String(20), nullable=False, default="gateway")
    admin_fee: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)

    payments: Mapped[list[Payment]] = relationship(back_populates="payment_method")


class Billing(Base):
    __tablename__ = "billing"
    __table_args__ = (
        UniqueConstraint("mahasiswa_id", "semester", name="uq_billing_mahasiswa_semester"),
        CheckConstraint("base_amount > 0", name="ck_billing_base_amount"),
        CheckConstraint("penalty_amount >= 0", name="ck_billing_penalty_amount"),
        CheckConstraint("total_amount > 0", name="ck_billing_total_amount"),
        CheckConstraint("paid_amount >= 0", name="ck_billing_paid_amount"),
        CheckConstraint(
            "status IN ('unpaid', 'partial', 'paid', 'overdue')",
            name="ck_billing_status",
        ),
        Index("idx_billing_status", "status"),
        Index("idx_billing_semester", "semester"),
        Index("idx_billing_due_date", "due_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    billing_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    mahasiswa_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("mahasiswa.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    semester: Mapped[str] = mapped_column(String(30), nullable=False)
    semester_start: Mapped[date] = mapped_column(Date, nullable=False)
    base_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    penalty_amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_amount: Mapped[int] = mapped_column(Integer, nullable=False)
    paid_amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(15), nullable=False, default=BillingStatus.UNPAID.value)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.now, onupdate=datetime.now
    )

    mahasiswa: Mapped[Mahasiswa] = relationship(back_populates="billings")
    payments: Mapped[list[Payment]] = relationship(back_populates="billing", cascade="all, delete-orphan")

    @property
    def total(self) -> int:
        """Alias kompatibel untuk `billing.total` sesuai spesifikasi Step 2."""
        return self.total_amount

    @property
    def remaining_amount(self) -> int:
        return max(0, self.total_amount - self.paid_amount)


class Payment(Base):
    __tablename__ = "payment"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payment_amount"),
        CheckConstraint("source IN ('manual', 'webhook')", name="ck_payment_source"),
        CheckConstraint("status IN ('success', 'pending', 'failed')", name="ck_payment_status"),
        Index("idx_payment_paid_at", "paid_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    billing_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("billing.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    payment_method_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("payment_method.id", ondelete="RESTRICT"), nullable=False
    )
    transaction_id: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default=PaymentSource.MANUAL.value)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=PaymentTxStatus.SUCCESS.value)
    paid_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)

    billing: Mapped[Billing] = relationship(back_populates="payments")
    payment_method: Mapped[PaymentMethod] = relationship(back_populates="payments")


class KrsEnrollment(Base):
    __tablename__ = "krs_enrollment"
    __table_args__ = (
        UniqueConstraint("mahasiswa_id", "semester", name="uq_krs_mahasiswa_semester"),
        CheckConstraint("total_sks > 0 AND total_sks <= 24", name="ck_krs_total_sks"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mahasiswa_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("mahasiswa.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    semester: Mapped[str] = mapped_column(String(30), nullable=False)
    mata_kuliah: Mapped[str] = mapped_column(Text, nullable=False)
    total_sks: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="approved")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)

    mahasiswa: Mapped[Mahasiswa] = relationship(back_populates="krs_enrollments")


class EmailLog(Base):
    __tablename__ = "email_log"
    __table_args__ = (
        CheckConstraint("email_type IN ('receipt', 'reminder')", name="ck_email_log_type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mahasiswa_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("mahasiswa.id", ondelete="SET NULL"), nullable=True
    )
    billing_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("billing.id", ondelete="SET NULL"), nullable=True
    )
    recipient_email: Mapped[str] = mapped_column(String(120), nullable=False)
    email_type: Mapped[str] = mapped_column(String(20), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    delivery_status: Mapped[str] = mapped_column(String(20), nullable=False, default="simulated")
    receipt_file_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
