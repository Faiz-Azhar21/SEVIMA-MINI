"""Service Manajemen Nilai — satu pintu untuk input dan edit nilai dengan audit trail."""

from __future__ import annotations

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.models.akademik import Jadwal, KRS, KRSDetail
from app.models.nilai import GradeHistory, SkalaNilai
from app.ports.presensi import MIN_PRESENSI, PresensiPort


class GradeError(Exception):
    """Base exception untuk seluruh pelanggaran aturan bisnis modul nilai."""

    status_code: int = 400


class GradeValidationError(GradeError):
    status_code: int = 400


class GradeForbiddenError(GradeError):
    status_code: int = 403


class GradeNotFoundError(GradeError):
    status_code: int = 404


def is_pengampu(db: Session, dosen_id: int, kelas_id: int) -> bool:
    """Periksa kepemilikan kelas: dosen terikat ke kelas lewat tabel jadwal (Minggu 7)."""
    return bool(
        db.scalar(
            select(
                exists().where(
                    Jadwal.kelas_id == kelas_id,
                    Jadwal.dosen_id == dosen_id,
                )
            )
        )
    )


class GradeService:
    """Satu pintu untuk input & edit nilai dengan 2 penjaga + audit trail atomik."""

    def __init__(self, db: Session, presensi: PresensiPort) -> None:
        self.db = db
        self.presensi = presensi

    def _detail_terkunci(self, kelas_id: int, nim: str) -> KRSDetail:
        """Ambil baris krs_detail mahasiswa di kelas terkait dengan SELECT ... FOR UPDATE."""
        detail = self.db.scalar(
            select(KRSDetail)
            .join(KRS, KRSDetail.krs_id == KRS.id)
            .where(KRSDetail.kelas_id == kelas_id, KRS.nim == nim)
            .with_for_update()
        )
        if detail is None:
            raise GradeNotFoundError(f"{nim} tidak terdaftar di kelas ini")
        return detail

    def input_nilai(
        self,
        dosen_id: int,
        kelas_id: int,
        nim: str,
        huruf: str,
        alasan: str | None = None,
    ) -> KRSDetail:
        """Input pertama atau edit nilai mahasiswa pada suatu kelas.

        Urutan pemeriksaan disengaja:
        1. Otorisasi dosen pengampu (403) sebelum membaca data mahasiswa.
        2. Keberadaan peserta di kelas + row lock FOR UPDATE (404).
        3. Presensi >= 75% melalui PresensiPort (400).
        4. Validasi huruf terhadap tabel skala_nilai (400).
        5. Idempotensi: jika nilai baru sama dengan nilai lama, tidak ada perubahan.
        6. Jika edit nilai lama, alasan wajib diisi (400).
        7. Simpan nilai + baris grade_history dalam satu transaksi atomik.
        """
        if not is_pengampu(self.db, dosen_id, kelas_id):
            raise GradeForbiddenError("Bukan dosen pengampu kelas ini")  # 403

        detail = self._detail_terkunci(kelas_id, nim)  # 404 + FOR UPDATE

        if self.presensi.persentase(nim, kelas_id) < MIN_PRESENSI:
            raise GradeValidationError("Presensi masih di bawah 75%")  # 400

        if self.db.get(SkalaNilai, huruf) is None:
            raise GradeValidationError(f"Nilai huruf '{huruf}' tidak terdaftar pada skala nilai")

        if detail.nilai == huruf:
            return detail  # tak ada perubahan

        alasan_bersih = alasan.strip() if alasan and alasan.strip() else None
        if detail.nilai is not None and alasan_bersih is None:
            raise GradeValidationError("Perubahan nilai wajib disertai alasan")

        nilai_lama = detail.nilai
        detail.nilai = huruf
        self.db.add(
            GradeHistory(
                grade_id=detail.id,
                old_value=nilai_lama,
                new_value=huruf,
                changed_by=dosen_id,
                reason=alasan_bersih,
            )
        )
        self.db.commit()  # nilai + history: satu transaksi
        return detail
