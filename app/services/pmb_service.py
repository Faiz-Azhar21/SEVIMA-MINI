"""Layanan bisnis PMB berbasis OOP untuk mengenkapsulasi aturan state machine."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import CalonMahasiswa, JalurMasuk, ProgramStudi, StatusPMB
from app.schemas import RegisterIn
from app.services.nim_generator import KODE_PRODI_REGEX, generate_nim


class PMBService:
    """Service OOP yang memusatkan seluruh aturan bisnis & transisi status modul PMB."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def register(self, payload: RegisterIn) -> CalonMahasiswa:
        """Mendaftarkan calon mahasiswa baru dengan status awal `pending`."""
        normalized_email = str(payload.email).strip().lower()

        prodi = self.db.get(ProgramStudi, payload.program_studi_id)
        if prodi is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Program studi tidak ditemukan",
            )

        jalur = self.db.scalars(
            select(JalurMasuk).where(JalurMasuk.kode == payload.jalur_masuk.value)
        ).one_or_none()
        if jalur is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Jalur masuk tidak terdaftar di sistem",
            )

        existing = self.db.scalars(
            select(CalonMahasiswa).where(CalonMahasiswa.email == normalized_email)
        ).one_or_none()
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email sudah terdaftar",
            )

        calon = CalonMahasiswa(
            nama_lengkap=payload.nama_lengkap,
            email=normalized_email,
            phone=payload.phone,
            tanggal_lahir=payload.tanggal_lahir,
            alamat=payload.alamat,
            program_studi_id=payload.program_studi_id,
            jalur_masuk=payload.jalur_masuk.value,
            status=StatusPMB.PENDING,
        )
        self.db.add(calon)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email sudah terdaftar",
            ) from exc

        self.db.refresh(calon)
        return calon

    def get_status(self, calon_id: int) -> CalonMahasiswa:
        """Mengambil data pendaftar untuk cek status pendaftaran."""
        calon = self.db.get(CalonMahasiswa, calon_id)
        if calon is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pendaftar tidak ditemukan",
            )
        return calon

    def approve(self, calon_id: int, max_retries: int = 3) -> CalonMahasiswa:
        """Menyetujui pendaftar (`pending` -> `approved`) dan menghasilkan NIM atomik.

        - Idempotent: jika status sudah `approved`, langsung kembalikan data + NIM lama
          tanpa menaikkan counter.
        - State guard: jika status `rejected`, tolak dengan 409 Conflict.
        - Data guard: jika prodi hilang atau kode prodi bukan 3 digit angka, tolak dengan 400.
        - Concurrency guard: row lock (`with_for_update=True`) + transaksi tunggal + retry
          pada `IntegrityError` (maksimal `max_retries` kali).
        """
        for attempt in range(max_retries):
            try:
                calon = self.db.get(CalonMahasiswa, calon_id, with_for_update=True)
                if calon is None:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Pendaftar tidak ditemukan",
                    )

                if calon.status == StatusPMB.APPROVED:
                    return calon

                if calon.status != StatusPMB.PENDING:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Status bukan pending",
                    )

                prodi = self.db.get(ProgramStudi, calon.program_studi_id)
                if prodi is None or not re.fullmatch(KODE_PRODI_REGEX, prodi.kode):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Kode program studi tidak valid untuk pembuatan NIM (harus 3 digit angka)",
                    )

                approved_at = datetime.now(timezone.utc)
                try:
                    nim = generate_nim(approved_at.year, prodi.kode, self.db)
                except ValueError as exc:
                    self.db.rollback()
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=str(exc),
                    ) from exc

                calon.approved_at = approved_at
                calon.nim = nim
                calon.status = StatusPMB.APPROVED

                self.db.commit()
                self.db.refresh(calon)
                return calon

            except IntegrityError as exc:
                self.db.rollback()
                if attempt == max_retries - 1:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Konflik pembuatan NIM bersamaan, silakan coba kembali",
                    ) from exc

        raise HTTPException(  # pragma: no cover - defensive fallback
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Gagal memproses persetujuan pendaftar",
        )

    def reject(self, calon_id: int) -> CalonMahasiswa:
        """Menolak pendaftar (`pending` -> `rejected`).

        - Idempotent: jika sudah `rejected`, kembalikan data tanpa error.
        - Terminal guard: jika sudah `approved`, tolak dengan 409 Conflict.
        """
        calon = self.db.get(CalonMahasiswa, calon_id, with_for_update=True)
        if calon is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pendaftar tidak ditemukan",
            )

        if calon.status == StatusPMB.REJECTED:
            return calon

        if calon.status != StatusPMB.PENDING:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Pendaftar yang sudah approved tidak dapat ditolak",
            )

        calon.status = StatusPMB.REJECTED
        self.db.commit()
        self.db.refresh(calon)
        return calon

    def get_stats(self) -> dict[str, object]:
        """Menghitung statistik pendaftar langsung di database dengan GROUP BY & outerjoin."""
        per_status_rows = self.db.execute(
            select(CalonMahasiswa.status, func.count(CalonMahasiswa.id)).group_by(
                CalonMahasiswa.status
            )
        ).all()

        per_prodi_rows = self.db.execute(
            select(ProgramStudi.nama, func.count(CalonMahasiswa.id))
            .outerjoin(CalonMahasiswa, ProgramStudi.id == CalonMahasiswa.program_studi_id)
            .group_by(ProgramStudi.id, ProgramStudi.nama)
        ).all()

        per_jalur_rows = self.db.execute(
            select(JalurMasuk.kode, func.count(CalonMahasiswa.id))
            .outerjoin(CalonMahasiswa, JalurMasuk.kode == CalonMahasiswa.jalur_masuk)
            .group_by(JalurMasuk.kode)
        ).all()

        per_status = {member.value: 0 for member in StatusPMB}
        for status_enum, count in per_status_rows:
            key = status_enum.value if isinstance(status_enum, StatusPMB) else str(status_enum)
            per_status[key] = count

        return {
            "total": sum(per_status.values()),
            "per_status": per_status,
            "per_prodi": {nama: count for nama, count in per_prodi_rows},
            "per_jalur_masuk": {kode: count for kode, count in per_jalur_rows},
        }
