from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from app.database import Base

class ProgramStudi(Base):
    __tablename__ = "program_studi"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    kode = Column(String(3), unique=True, nullable=False, index=True)
    nama = Column(String(100), nullable=False)
    fakultas = Column(String(100), nullable=False)

    calon_mahasiswa = relationship("CalonMahasiswa", back_populates="program_studi")

    def __repr__(self):
        return f"<ProgramStudi {self.kode} - {self.nama}>"
