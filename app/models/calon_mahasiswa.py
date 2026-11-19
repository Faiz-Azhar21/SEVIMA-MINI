import enum
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    Date,
    Text,
    DateTime,
    ForeignKey,
    Enum as SqlEnum,
    CheckConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

def utcnow():
    return datetime.now(timezone.utc)

class StatusPendaftaran(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

class CalonMahasiswa(Base):
    __tablename__ = "calon_mahasiswa"
    __table_args__ = (
        CheckConstraint(
            "(phone LIKE '08%') OR (phone LIKE '+62%') OR (phone LIKE '62%')",
            name="check_phone_indonesia"
        ),
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="check_status_enum"
        ),
    )

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    nama_lengkap = Column(String(150), nullable=False)
    email = Column(String(150), unique=True, nullable=False, index=True)
    phone = Column(String(20), nullable=False)
    tanggal_lahir = Column(Date, nullable=False)
    alamat = Column(Text, nullable=False)
    program_studi_id = Column(Integer, ForeignKey("program_studi.id"), nullable=False)
    jalur_masuk_id = Column(Integer, ForeignKey("jalur_masuk.id"), nullable=False)
    status = Column(
        SqlEnum(StatusPendaftaran, values_callable=lambda x: [e.value for e in x]),
        default=StatusPendaftaran.PENDING.value,
        nullable=False
    )
    nim = Column(String(20), unique=True, nullable=True, index=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    approved_at = Column(DateTime, nullable=True)

    program_studi = relationship("ProgramStudi", back_populates="calon_mahasiswa")
    jalur_masuk_rel = relationship("JalurMasuk", back_populates="calon_mahasiswa")

    @property
    def jalur_masuk(self) -> str:
        return self.jalur_masuk_rel.kode if self.jalur_masuk_rel else ""

    def __repr__(self):
        return f"<CalonMahasiswa {self.id} - {self.nama_lengkap} - Status: {self.status}>"
