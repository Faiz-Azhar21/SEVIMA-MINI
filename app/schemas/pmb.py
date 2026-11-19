import re
from datetime import date, datetime
from typing import Optional, Dict
from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict

INDONESIAN_PHONE_REGEX = re.compile(r"^(\+62|62|08)[0-9]{8,13}$")

class ProgramStudiBase(BaseModel):
    kode: str = Field(..., min_length=3, max_length=3, description="Kode program studi (3 karakter)")
    nama: str = Field(..., min_length=3, max_length=100)
    fakultas: str = Field(..., min_length=3, max_length=100)

class ProgramStudiResponse(ProgramStudiBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

class JalurMasukBase(BaseModel):
    kode: str = Field(..., description="Kode jalur masuk (SNBP, SNBT, Mandiri)")
    nama: str
    keterangan: Optional[str] = None

class JalurMasukResponse(JalurMasukBase):
    id: int
    model_config = ConfigDict(from_attributes=True)

class CalonMahasiswaCreate(BaseModel):
    nama_lengkap: str = Field(..., min_length=2, max_length=150, description="Nama lengkap calon mahasiswa")
    email: EmailStr = Field(..., description="Email unik calon mahasiswa")
    phone: str = Field(..., description="Nomor telepon format Indonesia (+62 / 62 / 08)")
    tanggal_lahir: date = Field(..., description="Tanggal lahir (YYYY-MM-DD)")
    alamat: str = Field(..., min_length=5, description="Alamat lengkap")
    program_studi_id: int = Field(..., description="ID Program Studi pilihan")
    jalur_masuk: Optional[str] = Field(None, description="Kode Jalur Masuk: SNBP / SNBT / Mandiri")
    jalur_masuk_id: Optional[int] = Field(None, description="ID Jalur Masuk alternatif")

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        clean_phone = v.strip().replace(" ", "").replace("-", "")
        if not INDONESIAN_PHONE_REGEX.match(clean_phone):
            raise ValueError(
                "Format nomor telepon tidak valid. Gunakan format Indonesia (contoh: 081234567890 atau +6281234567890)"
            )
        return clean_phone

    @field_validator("jalur_masuk")
    @classmethod
    def validate_jalur_masuk(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v_upper = v.strip().upper()
            valid_jalur = ["SNBP", "SNBT", "MANDIRI"]
            if v_upper not in valid_jalur:
                raise ValueError(f"Jalur masuk tidak valid. Pilihan: {', '.join(valid_jalur)}")
            return v_upper
        return v

class CalonMahasiswaResponse(BaseModel):
    id: int
    nama_lengkap: str
    email: str
    phone: str
    tanggal_lahir: date
    alamat: str
    program_studi_id: int
    jalur_masuk: str
    status: str
    nim: Optional[str] = None
    created_at: datetime
    approved_at: Optional[datetime] = None
    program_studi: Optional[ProgramStudiResponse] = None

    model_config = ConfigDict(from_attributes=True)

class ApproveResponse(BaseModel):
    id: int
    nama_lengkap: str
    status: str
    nim: str
    approved_at: datetime
    message: str = "Pendaftaran berhasil disetujui"

    model_config = ConfigDict(from_attributes=True)

class StatsResponse(BaseModel):
    total_pendaftar: int
    by_status: Dict[str, int]
    by_program_studi: Dict[str, int]
    by_jalur_masuk: Dict[str, int]
