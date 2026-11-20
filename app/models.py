"""ORM Models untuk Modul KRS (Kartu Rencana Studi) SEVIMA-Mini.

Mencakup 4 tabel utama (matakuliah, krs, krs_detail, prerequisite) beserta
tabel pendukung (riwayat_nilai, log_krs, notifikasi) dan composite index
untuk optimasi query prasyarat & konkurensi.
"""

from datetime import datetime, time, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.enums import Actor, JenisMK, KRSStatus
from app.exceptions import TransitionError
from app.state_machine import EDITABLE_STATUSES, TRANSITIONS


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Matakuliah(Base):
    """Master data mata kuliah beserta jadwal dan kategori (WAJIB/PILIHAN)."""

    __tablename__ = "matakuliah"
    __table_args__ = (
        CheckConstraint("sks BETWEEN 1 AND 6", name="ck_matakuliah_sks"),
        CheckConstraint("hari BETWEEN 1 AND 6", name="ck_matakuliah_hari"),
        CheckConstraint("jam_selesai > jam_mulai", name="ck_matakuliah_jam"),
        Index("idx_matakuliah_kode_induk", "kode_induk"),
    )

    kode_mk: Mapped[str] = mapped_column(String(20), primary_key=True)
    kode_induk: Mapped[str] = mapped_column(String(20), nullable=False)
    kelas: Mapped[str] = mapped_column(String(10), nullable=False, default="A")
    nama: Mapped[str] = mapped_column(String(120), nullable=False)
    sks: Mapped[int] = mapped_column(Integer, nullable=False)
    hari: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    jam_mulai: Mapped[time] = mapped_column(Time, nullable=False, default=time(8, 0))
    jam_selesai: Mapped[time] = mapped_column(Time, nullable=False, default=time(10, 0))
    jenis: Mapped[JenisMK] = mapped_column(
        SqlEnum(JenisMK), nullable=False, default=JenisMK.WAJIB
    )

    prerequisites: Mapped[list["Prerequisite"]] = relationship(
        "Prerequisite",
        foreign_keys="Prerequisite.kode_mk",
        back_populates="matakuliah",
        cascade="all, delete-orphan",
    )

    def __init__(self, **kwargs):
        # Memudahkan pembuatan objek di memori (mis. unit/property test)
        # tanpa wajib mengisi kode_induk, kelas, hari, jam, atau jenis.
        if "kode_induk" not in kwargs and "kode_mk" in kwargs:
            kwargs["kode_induk"] = kwargs["kode_mk"]
        kwargs.setdefault("kelas", "A")
        kwargs.setdefault("hari", 1)
        kwargs.setdefault("jam_mulai", time(8, 0))
        kwargs.setdefault("jam_selesai", time(10, 0))
        kwargs.setdefault("jenis", JenisMK.WAJIB)
        super().__init__(**kwargs)

    @property
    def effective_kode_induk(self) -> str:
        return self.kode_induk or self.kode_mk


class Prerequisite(Base):
    """Relasi prasyarat mata kuliah (kode_mk membutuhkan prasyarat_kode_mk)."""

    __tablename__ = "prerequisite"
    __table_args__ = (
        CheckConstraint("kode_mk <> prasyarat_kode_mk", name="ck_prereq_not_self"),
        Index(
            "idx_prerequisite_kode_mk",
            "kode_mk",
            "prasyarat_kode_mk",
            "nilai_minimal",
        ),
    )

    kode_mk: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("matakuliah.kode_mk", ondelete="CASCADE"),
        primary_key=True,
    )
    prasyarat_kode_mk: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("matakuliah.kode_mk", ondelete="CASCADE"),
        primary_key=True,
    )
    nilai_minimal: Mapped[str] = mapped_column(String(2), nullable=False, default="C")

    matakuliah: Mapped[Matakuliah] = relationship(
        "Matakuliah", foreign_keys=[kode_mk], back_populates="prerequisites"
    )
    prasyarat: Mapped[Matakuliah] = relationship(
        "Matakuliah", foreign_keys=[prasyarat_kode_mk]
    )


class RiwayatNilai(Base):
    """Riwayat nilai mahasiswa pada semester-semester sebelumnya."""

    __tablename__ = "riwayat_nilai"
    __table_args__ = (
        CheckConstraint("semester >= 1", name="ck_riwayat_semester"),
        Index(
            "idx_riwayat_nilai_nim_mk_sem",
            "nim",
            "kode_mk",
            "semester",
            "nilai_huruf",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nim: Mapped[str] = mapped_column(String(20), nullable=False)
    kode_mk: Mapped[str] = mapped_column(
        String(20), ForeignKey("matakuliah.kode_mk", ondelete="RESTRICT"), nullable=False
    )
    semester: Mapped[int] = mapped_column(Integer, nullable=False)
    nilai_huruf: Mapped[str] = mapped_column(String(2), nullable=False)


class KRS(Base):
    """Header KRS mahasiswa dengan State Machine dan Optimistic Locking."""

    __tablename__ = "krs"
    __table_args__ = (
        UniqueConstraint("nim", "semester", name="uq_krs_nim_semester"),
        Index("idx_krs_nim_semester", "nim", "semester"),
        Index("idx_krs_dosen_pa", "dosen_pa_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nim: Mapped[str] = mapped_column(String(20), nullable=False)
    semester: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    dosen_pa_id: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[KRSStatus] = mapped_column(
        SqlEnum(KRSStatus), nullable=False, default=KRSStatus.DRAFT
    )
    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    catatan_revisi: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    diubah_pada: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    details: Mapped[list["KRSDetail"]] = relationship(
        "KRSDetail",
        back_populates="krs",
        cascade="all, delete-orphan",
    )
    logs: Mapped[list["LogKRS"]] = relationship(
        "LogKRS",
        back_populates="krs",
        cascade="all, delete-orphan",
    )

    __mapper_args__ = {"version_id_col": version}

    def __init__(self, **kwargs):
        kwargs.setdefault("status", KRSStatus.DRAFT)
        kwargs.setdefault("semester", 1)
        kwargs.setdefault("dosen_pa_id", 1)
        kwargs.setdefault("diubah_pada", _utc_now())
        kwargs.setdefault("version", 1)
        super().__init__(**kwargs)

    @property
    def is_editable(self) -> bool:
        """KRS hanya bisa diubah isinya saat status DRAFT atau REVISION."""
        return self.status in EDITABLE_STATUSES

    @property
    def total_sks(self) -> int:
        """Total SKS seluruh mata kuliah dalam KRS."""
        return sum(d.matakuliah.sks for d in self.details if d.matakuliah is not None)

    def cek_transisi(self, target: KRSStatus, actor: Actor) -> None:
        """Validasi apakah perpindahan status diizinkan tanpa mengubah state.

        Dipisah dari `transition()` agar service bisa fail-fast sebelum
        menjalankan validasi yang mahal.
        """
        allowed_targets = TRANSITIONS.get((self.status, actor), set())
        if target not in allowed_targets:
            raise TransitionError(
                f"Transisi tidak diizinkan: {self.status.name} ke {target.name}"
            )

    def transition(self, target: KRSStatus, actor: Actor) -> None:
        """Satu-satunya pintu sah untuk mengubah `self.status`."""
        self.cek_transisi(target, actor)
        self.status = target
        self.diubah_pada = _utc_now()

    def sentuh_perubahan(self) -> None:
        """Memperbarui timestamp `diubah_pada` agar kolom `version` ikut naik
        ketika baris anak (`krs_detail`) ditambah atau dihapus."""
        self.diubah_pada = _utc_now()


class KRSDetail(Base):
    """Tabel penghubung many-to-many antara KRS mahasiswa dan Matakuliah."""

    __tablename__ = "krs_detail"
    __table_args__ = (
        UniqueConstraint("krs_id", "kode_mk", name="uq_krs_detail_krs_mk"),
        Index("idx_krs_detail_krs_id", "krs_id", "kode_mk"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    krs_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("krs.id", ondelete="CASCADE"), nullable=False
    )
    kode_mk: Mapped[str] = mapped_column(
        String(20),
        ForeignKey("matakuliah.kode_mk", ondelete="RESTRICT"),
        nullable=False,
    )

    krs: Mapped[KRS] = relationship("KRS", back_populates="details")
    matakuliah: Mapped[Matakuliah] = relationship("Matakuliah")


class LogKRS(Base):
    """Audit trail aksi pada KRS (submit, approve, revise)."""

    __tablename__ = "log_krs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    krs_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("krs.id", ondelete="CASCADE"), nullable=False
    )
    aksi: Mapped[str] = mapped_column(String(32), nullable=False)
    aktor: Mapped[str] = mapped_column(String(64), nullable=False)
    catatan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )

    krs: Mapped[KRS] = relationship("KRS", back_populates="logs")


class Notifikasi(Base):
    """Antrean notifikasi di database (dikirim setelah commit via Observer di Minggu 7-8)."""

    __tablename__ = "notifikasi"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nim: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    pesan: Mapped[str] = mapped_column(Text, nullable=False)
    terkirim: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utc_now
    )
