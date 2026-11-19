from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from app.database import Base

class JalurMasuk(Base):
    __tablename__ = "jalur_masuk"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    kode = Column(String(20), unique=True, nullable=False, index=True)
    nama = Column(String(100), nullable=False)
    keterangan = Column(String(255), nullable=True)

    calon_mahasiswa = relationship("CalonMahasiswa", back_populates="jalur_masuk_rel")

    def __repr__(self):
        return f"<JalurMasuk {self.kode} - {self.nama}>"
