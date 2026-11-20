"""Model ORM SQLAlchemy 2.0 untuk modul PMB (Penerimaan Mahasiswa Baru)."""

from __future__ import annotations

import enum
from datetime import date, datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class StatusPMB(str, enum.Enum):
    """Status pendaftaran calon mahasiswa (state machine)."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class JalurMasukEnum(str, enum.Enum):
    """Jalur masuk resmi PMB."""

    SNBP = "SNBP"
    SNBT = "SNBT"
    MANDIRI = "Mandiri"


class ProgramStudi(Base):
    """Master data program studi dengan kode 3 digit untuk pembentuk NIM."""

    __tablename__ = "program_studi"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kode: Mapped[str] = mapped_column(String(10), unique=True, nullable=False, index=True)
    nama: Mapped[str] = mapped_column(String(120), nullable=False)
    fakultas: Mapped[str] = mapped_column(String(120), nullable=False)

    calon_mahasiswa_list: Mapped[list[CalonMahasiswa]] = relationship(
        back_populates="program_studi",
    )


class JalurMasuk(Base):
    """Master data jalur masuk (SNBP, SNBT, Mandiri)."""

    __tablename__ = "jalur_masuk"
    __table_args__ = (
        CheckConstraint(
            "kode IN ('SNBP', 'SNBT', 'Mandiri')",
            name="ck_jalur_masuk_kode",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kode: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    nama: Mapped[str] = mapped_column(String(100), nullable=False)
    deskripsi: Mapped[str | None] = mapped_column(Text, nullable=True)

    calon_mahasiswa_list: Mapped[list[CalonMahasiswa]] = relationship(
        back_populates="jalur_masuk_ref",
    )


class CalonMahasiswa(Base):
    """Entitas pendaftar calon mahasiswa baru beserta status seleksi & NIM."""

    __tablename__ = "calon_mahasiswa"
    __table_args__ = (
        CheckConstraint(
            "email LIKE '%_@__%.__%'",
            name="ck_calon_email_format",
        ),
        CheckConstraint(
            "(phone LIKE '08%' OR phone LIKE '+628%' OR phone LIKE '628%') "
            "AND length(phone) >= 10 AND length(phone) <= 15",
            name="ck_calon_phone_indonesia",
        ),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_calon_status_enum",
        ),
        CheckConstraint(
            "jalur_masuk IN ('SNBP', 'SNBT', 'Mandiri')",
            name="ck_calon_jalur_masuk_enum",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nama_lengkap: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    phone: Mapped[str] = mapped_column(String(20), nullable=False)
    tanggal_lahir: Mapped[date] = mapped_column(Date, nullable=False)
    alamat: Mapped[str] = mapped_column(Text, nullable=False)
    program_studi_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("program_studi.id", ondelete="RESTRICT"),
        nullable=False,
    )
    jalur_masuk: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("jalur_masuk.kode", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[StatusPMB] = mapped_column(
        SAEnum(
            StatusPMB,
            name="status_pmb_enum",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=StatusPMB.PENDING,
    )
    nim: Mapped[str | None] = mapped_column(
        String(12),
        unique=True,
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    program_studi: Mapped[ProgramStudi] = relationship(
        back_populates="calon_mahasiswa_list",
    )
    jalur_masuk_ref: Mapped[JalurMasuk] = relationship(
        back_populates="calon_mahasiswa_list",
    )


class NimCounter(Base):
    """Tabel counter nomor urut NIM per kombinasi (tahun, kode_prodi) untuk row-level locking."""

    __tablename__ = "nim_counter"
    __table_args__ = (
        CheckConstraint(
            "last_number >= 0 AND last_number <= 9999",
            name="ck_nim_counter_range",
        ),
    )

    tahun: Mapped[int] = mapped_column(Integer, primary_key=True)
    kode_prodi: Mapped[str] = mapped_column(String(3), primary_key=True)
    last_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
