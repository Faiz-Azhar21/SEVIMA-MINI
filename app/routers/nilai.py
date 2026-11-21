"""Router API untuk input nilai, perhitungan IPS/IPK, dan riwayat audit trail."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.akademik import Dosen, Jadwal, Kelas, KRS, KRSDetail, Mahasiswa, MataKuliah
from app.ports.presensi import MIN_PRESENSI, PresensiPort
from app.repositories.nilai_repo import NilaiRepo
from app.routers.deps import (
    get_current_dosen,
    get_db,
    get_gpa,
    get_grade_service,
    get_nilai_repo,
    get_presensi_port,
)
from app.services.gpa_calculator import GPACalculator
from app.services.grade_service import GradeService


class NilaiIn(BaseModel):
    """Validasi awal input nilai via Pydantic (sumber kebenaran tetap FK skala_nilai)."""

    huruf: str = Field(pattern="^[A-E]$")  # "A+", "a", "F" -> 422
    alasan: str | None = Field(default=None, max_length=255)


class NilaiOut(BaseModel):
    nim: str
    kode_mk: str
    huruf: str


class IPKOut(BaseModel):
    nim: str
    ipk: str  # dikirim sebagai string ("3.08") agar klien tidak mengubahnya jadi float


class IPSOut(BaseModel):
    nim: str
    semester: str
    ips: str


class RiwayatNilaiOut(BaseModel):
    history_id: int
    grade_id: int
    nim: str
    semester: str
    kode_mk: str
    nama_mk: str
    old_value: str | None
    new_value: str
    pengubah: str
    changed_at: str
    reason: str | None


class PesertaKelasOut(BaseModel):
    nim: str
    nama: str
    presensi: str
    terkunci: bool
    alasan_terkunci: str | None
    nilai: str | None
    ipk_saat_ini: str


class KelasInfoOut(BaseModel):
    id: int
    kode_mk: str
    nama_mk: str
    nama_kelas: str
    semester: str
    dosen_ids: list[int]
    dosen_nama: list[str]


class DosenInfoOut(BaseModel):
    id: int
    nidn: str
    nama: str


kelas_router = APIRouter(prefix="/api/kelas", tags=["nilai"])
mahasiswa_router = APIRouter(prefix="/api/mahasiswa", tags=["gpa"])
referensi_router = APIRouter(prefix="/api", tags=["referensi"])


@kelas_router.put("/{kelas_id}/nilai/{nim}", response_model=NilaiOut)
def input_nilai(
    kelas_id: int,
    nim: str,
    data: NilaiIn,
    dosen: Dosen = Depends(get_current_dosen),
    svc: GradeService = Depends(get_grade_service),
) -> NilaiOut:
    """Tetapkan atau ubah nilai mahasiswa pada suatu kelas (idempotent PUT)."""
    detail = svc.input_nilai(dosen.id, kelas_id, nim, data.huruf, data.alasan)
    assert detail.nilai is not None
    return NilaiOut(nim=nim, kode_mk=detail.kode_mk, huruf=detail.nilai)


@kelas_router.get("/{kelas_id}/peserta", response_model=list[PesertaKelasOut])
def daftar_peserta_kelas(
    kelas_id: int,
    db: Session = Depends(get_db),
    presensi: PresensiPort = Depends(get_presensi_port),
    calc: GPACalculator = Depends(get_gpa),
) -> list[PesertaKelasOut]:
    """Daftar peserta kelas beserta presensi, status kunci, nilai, dan IPK live untuk form web."""
    if db.get(Kelas, kelas_id) is None:
        raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")

    stmt = (
        select(Mahasiswa.nim, Mahasiswa.nama, KRSDetail.nilai)
        .join(KRS, KRS.nim == Mahasiswa.nim)
        .join(KRSDetail, KRSDetail.krs_id == KRS.id)
        .where(KRSDetail.kelas_id == kelas_id)
        .order_by(Mahasiswa.nim)
    )
    hasil: list[PesertaKelasOut] = []
    for nim, nama, nilai in db.execute(stmt):
        persen = presensi.persentase(nim, kelas_id)
        terkunci = persen < MIN_PRESENSI
        hasil.append(
            PesertaKelasOut(
                nim=nim,
                nama=nama,
                presensi=f"{persen}%",
                terkunci=terkunci,
                alasan_terkunci="terkunci - presensi < 75%" if terkunci else None,
                nilai=nilai,
                ipk_saat_ini=str(calc.calculate_ipk(nim)),
            )
        )
    return hasil


@mahasiswa_router.get("/{nim}/ipk", response_model=IPKOut)
def get_ipk(
    nim: str,
    calc: GPACalculator = Depends(get_gpa),
) -> IPKOut:
    """Hitung IPK kumulatif secara compute-on-read dan kirim sebagai string."""
    return IPKOut(nim=nim, ipk=str(calc.calculate_ipk(nim)))


@mahasiswa_router.get("/{nim}/ips/{semester}", response_model=IPSOut)
def get_ips(
    nim: str,
    semester: str,
    calc: GPACalculator = Depends(get_gpa),
) -> IPSOut:
    """Hitung IPS untuk satu semester tertentu (termasuk nilai E)."""
    return IPSOut(nim=nim, semester=semester, ips=str(calc.calculate_ips(nim, semester)))


@mahasiswa_router.get("/{nim}/riwayat-nilai", response_model=list[RiwayatNilaiOut])
def get_riwayat_nilai(
    nim: str,
    repo: NilaiRepo = Depends(get_nilai_repo),
) -> list[RiwayatNilaiOut]:
    """Ambil audit trail perubahan nilai per mahasiswa dari view v_riwayat_nilai."""
    rows = repo.riwayat_nilai(nim)
    return [
        RiwayatNilaiOut(
            history_id=r.history_id,
            grade_id=r.grade_id,
            nim=r.nim,
            semester=r.semester,
            kode_mk=r.kode_mk,
            nama_mk=r.nama_mk,
            old_value=r.old_value,
            new_value=r.new_value,
            pengubah=r.pengubah,
            changed_at=r.changed_at,
            reason=r.reason,
        )
        for r in rows
    ]


@referensi_router.get("/kelas", response_model=list[KelasInfoOut])
def list_kelas(db: Session = Depends(get_db)) -> list[KelasInfoOut]:
    """Daftar kelas beserta dosen pengampunya untuk dropdown form web."""
    kelas_rows = db.scalars(select(Kelas).order_by(Kelas.id)).all()
    hasil: list[KelasInfoOut] = []
    for k in kelas_rows:
        mk = db.get(MataKuliah, k.kode_mk)
        jadwal_rows = db.scalars(select(Jadwal).where(Jadwal.kelas_id == k.id)).all()
        dosen_ids = sorted({j.dosen_id for j in jadwal_rows})
        dosen_nama = [
            d.nama for d_id in dosen_ids if (d := db.get(Dosen, d_id)) is not None
        ]
        hasil.append(
            KelasInfoOut(
                id=k.id,
                kode_mk=k.kode_mk,
                nama_mk=mk.nama_mk if mk else k.kode_mk,
                nama_kelas=k.nama_kelas,
                semester=k.semester,
                dosen_ids=dosen_ids,
                dosen_nama=dosen_nama,
            )
        )
    return hasil


@referensi_router.get("/dosen", response_model=list[DosenInfoOut])
def list_dosen(db: Session = Depends(get_db)) -> list[DosenInfoOut]:
    """Daftar dosen untuk simulasi login di form web sederhana."""
    rows = db.scalars(select(Dosen).order_by(Dosen.id)).all()
    return [DosenInfoOut(id=d.id, nidn=d.nidn, nama=d.nama) for d in rows]
