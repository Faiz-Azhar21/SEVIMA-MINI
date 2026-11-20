"""KRSManager Service — Inti logika bisnis, transaksi ACID, dan konkurensi."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.orm.exc import StaleDataError

from app.enums import Actor, HARI_NAMA, KRSStatus
from app.exceptions import (
    ForbiddenError,
    KRSError,
    KRSLockedError,
    NotFoundError,
    ValidationInputError,
)
from app.models import KRS, KRSDetail, LogKRS, Matakuliah, Notifikasi
from app.validators import (
    MAX_SKS_PER_SEMESTER,
    KRSContext,
    PrerequisiteValidator,
    ValidationResult,
    Validator,
    build_validation_chain,
    is_schedule_conflict,
)


class KRSManager:
    """Service layer pengelola siklus hidup KRS mahasiswa.

    Lapisan ini tidak mengetahui detail HTTP (Framework-agnostic) sehingga
    mudah diuji secara langsung lewat unit & integration test.
    """

    def __init__(
        self,
        db: Session,
        validator_chain: Optional[Validator] = None,
        max_sks: int = MAX_SKS_PER_SEMESTER,
    ) -> None:
        self.db = db
        self.max_sks = max_sks
        self._validator_chain = validator_chain or build_validation_chain(
            max_sks=max_sks
        )

    def _krs_terkunci(self, nim: str, semester: Optional[int] = None) -> KRS:
        """Mengambil baris KRS sambil menguncinya dengan SELECT ... FOR UPDATE
        (Pessimistic Lock) agar operasi mutasi aman dari race condition.
        """
        stmt = (
            select(KRS)
            .options(selectinload(KRS.details).selectinload(KRSDetail.matakuliah))
            .where(KRS.nim == nim)
        )
        if semester is not None:
            stmt = stmt.where(KRS.semester == semester)
        else:
            stmt = stmt.order_by(KRS.semester.desc())

        krs = self.db.execute(stmt.with_for_update()).scalars().first()
        if krs is None:
            raise NotFoundError(f"KRS untuk mahasiswa {nim} tidak ditemukan")
        return krs

    def get_krs(self, nim: str, semester: Optional[int] = None) -> KRS:
        """Membaca data KRS mahasiswa beserta detail mata kuliahnya."""
        stmt = (
            select(KRS)
            .options(selectinload(KRS.details).selectinload(KRSDetail.matakuliah))
            .where(KRS.nim == nim)
        )
        if semester is not None:
            stmt = stmt.where(KRS.semester == semester)
        else:
            stmt = stmt.order_by(KRS.semester.desc())

        krs = self.db.execute(stmt).scalars().first()
        if krs is None:
            raise NotFoundError(f"KRS untuk mahasiswa {nim} tidak ditemukan")
        return krs

    def add_course(
        self, nim: str, kode_mk: str, semester: Optional[int] = None
    ) -> KRS:
        """Menambahkan mata kuliah ke KRS mahasiswa dengan validasi Chain of Responsibility.

        Status KRS dicek SETELAH lock baris diperoleh untuk mencegah penambahan MK
        saat KRS sedang diajukan/disetujui di transaksi lain.
        """
        try:
            krs = self._krs_terkunci(nim, semester=semester)
            if not krs.is_editable:
                raise KRSLockedError(
                    f"KRS berstatus {krs.status.value} tidak bisa diubah"
                )

            mk = self.db.get(Matakuliah, kode_mk)
            if mk is None:
                raise NotFoundError(f"Mata kuliah {kode_mk} tidak ditemukan")

            ctx = KRSContext(
                nim=nim,
                details=list(krs.details),
                mk=mk,
                db=self.db,
                semester=krs.semester,
            )
            result = self._validator_chain.handle(ctx)
            if not result.ok:
                raise KRSError(result.message)

            detail = KRSDetail(krs_id=krs.id, kode_mk=mk.kode_mk)
            detail.matakuliah = mk
            krs.details.append(detail)
            # Sentuh baris induk agar kolom `version` (optimistic lock) ikut naik
            krs.sentuh_perubahan()

            self.db.commit()
            self.db.refresh(krs)
            return krs
        except StaleDataError as exc:
            self.db.rollback()
            raise KRSLockedError("KRS sudah berubah, muat ulang") from exc
        except Exception:
            self.db.rollback()
            raise

    def remove_course(
        self, nim: str, kode_mk: str, semester: Optional[int] = None
    ) -> KRS:
        """Menghapus mata kuliah dari KRS mahasiswa (hanya saat DRAFT/REVISION)."""
        try:
            krs = self._krs_terkunci(nim, semester=semester)
            if not krs.is_editable:
                raise KRSLockedError(
                    f"KRS berstatus {krs.status.value} tidak bisa diubah"
                )

            target = next((d for d in krs.details if d.kode_mk == kode_mk), None)
            if target is None:
                raise NotFoundError(
                    f"Mata kuliah {kode_mk} tidak ada di dalam KRS mahasiswa {nim}"
                )

            krs.details.remove(target)
            krs.sentuh_perubahan()

            self.db.commit()
            self.db.refresh(krs)
            return krs
        except StaleDataError as exc:
            self.db.rollback()
            raise KRSLockedError("KRS sudah berubah, muat ulang") from exc
        except Exception:
            self.db.rollback()
            raise

    def validate_krs(
        self, nim: str, semester: Optional[int] = None
    ) -> list[ValidationResult]:
        """Memeriksa SEMUA aturan bisnis untuk seluruh MK di KRS dan mengumpulkan
        seluruh kesalahan (mengembalikan list kosong jika semua valid).
        """
        krs = self.get_krs(nim, semester=semester)
        failures: list[ValidationResult] = []
        details = list(krs.details)

        # 1. Total SKS <= max_sks
        total_sks = sum(d.matakuliah.sks for d in details if d.matakuliah is not None)
        if total_sks > self.max_sks:
            failures.append(
                ValidationResult.fail(
                    f"Total SKS melebihi batas maksimal {self.max_sks} SKS "
                    f"(total saat ini {total_sks} SKS)"
                )
            )

        # 2. Double enrollment (kode_mk atau kode_induk duplikat)
        seen_kode: set[str] = set()
        seen_induk: dict[str, str] = {}
        for d in details:
            mk = d.matakuliah
            if mk is None:
                continue
            if mk.kode_mk in seen_kode:
                failures.append(
                    ValidationResult.fail(
                        f"Mata kuliah sudah diambil (double enrollment): "
                        f"{mk.nama} ({mk.kode_mk})"
                    )
                )
            elif mk.effective_kode_induk in seen_induk:
                failures.append(
                    ValidationResult.fail(
                        f"Double enrollment: {mk.nama} sudah diambil di kelas lain "
                        f"({seen_induk[mk.effective_kode_induk]})"
                    )
                )
            else:
                seen_kode.add(mk.kode_mk)
                seen_induk[mk.effective_kode_induk] = mk.kode_mk

        # 3. Prasyarat seluruh MK (nilai semester sebelumnya >= C)
        prereq_validator = PrerequisiteValidator()
        for d in details:
            mk = d.matakuliah
            if mk is None:
                continue
            ctx = KRSContext(
                nim=nim,
                details=details,
                mk=mk,
                db=self.db,
                semester=krs.semester,
            )
            res = prereq_validator.validate(ctx)
            if not res.ok:
                failures.append(res)

        # 4. Bentrok jadwal antar pasangan MK (i < j agar tidak duplikat)
        for i in range(len(details)):
            mk_a = details[i].matakuliah
            if mk_a is None:
                continue
            for j in range(i + 1, len(details)):
                mk_b = details[j].matakuliah
                if mk_b is None or mk_a.kode_mk == mk_b.kode_mk:
                    continue
                if is_schedule_conflict(mk_a, mk_b):
                    hari_str = HARI_NAMA.get(mk_a.hari, f"Hari {mk_a.hari}")
                    jam_a = (
                        f"{mk_a.jam_mulai.strftime('%H:%M')}-"
                        f"{mk_a.jam_selesai.strftime('%H:%M')}"
                    )
                    failures.append(
                        ValidationResult.fail(
                            f"Jadwal bentrok antara {mk_a.nama} dan {mk_b.nama} "
                            f"({hari_str} {jam_a})"
                        )
                    )

        return failures

    def submit_krs(self, nim: str, semester: Optional[int] = None) -> KRS:
        """Mengajukan KRS mahasiswa: DRAFT/REVISION -> SUBMITTED.

        Urutan penjagaan:
        1. Lock baris KRS (FOR UPDATE)
        2. Cek transisi lebih dulu (fail fast -> 409)
        3. Tolak KRS kosong (-> 400)
        4. Validasi ulang semua aturan untuk semua MK (-> 400)
        5. Pindah state via transition(), catat waktu & log, lalu commit
        """
        try:
            krs = self._krs_terkunci(nim, semester=semester)
            krs.cek_transisi(KRSStatus.SUBMITTED, Actor.MAHASISWA)

            if not krs.details:
                raise KRSError("KRS kosong: tambahkan minimal satu mata kuliah")

            gagal = self.validate_krs(nim, semester=krs.semester)
            if gagal:
                raise KRSError("; ".join(r.message for r in gagal))

            krs.transition(KRSStatus.SUBMITTED, Actor.MAHASISWA)
            krs.submitted_at = datetime.now(timezone.utc)
            self.db.add(
                LogKRS(
                    krs_id=krs.id,
                    aksi="submit",
                    aktor=f"mahasiswa:{nim}",
                )
            )
            self.db.commit()
            self.db.refresh(krs)
            return krs
        except StaleDataError as exc:
            self.db.rollback()
            raise KRSLockedError("KRS sudah berubah, muat ulang") from exc
        except Exception:
            self.db.rollback()
            raise

    def approve_krs(
        self,
        nim: str,
        dosen_pa_id: int,
        expected_version: Optional[int] = None,
        semester: Optional[int] = None,
    ) -> KRS:
        """Persetujuan KRS oleh Dosen PA dalam satu unit kerja transaksi ACID:
        ubah status -> catat waktu -> tulis LogKRS -> tulis Notifikasi -> commit.
        Jika salah satu gagal, seluruh operasi di-rollback.
        """
        try:
            krs = self._krs_terkunci(nim, semester=semester)
            if krs.dosen_pa_id != dosen_pa_id:
                raise ForbiddenError("Anda bukan dosen PA mahasiswa ini")

            if expected_version is not None and krs.version != expected_version:
                raise KRSLockedError("KRS sudah berubah, muat ulang")

            krs.transition(KRSStatus.APPROVED, Actor.DOSEN_PA)
            krs.approved_at = datetime.now(timezone.utc)
            self.db.add(
                LogKRS(
                    krs_id=krs.id,
                    aksi="approve",
                    aktor=f"dosen_pa:{dosen_pa_id}",
                )
            )
            self.db.add(
                Notifikasi(
                    nim=nim,
                    pesan="KRS Anda disetujui",
                )
            )
            self.db.commit()
            self.db.refresh(krs)
            return krs
        except StaleDataError as exc:
            self.db.rollback()
            raise KRSLockedError("KRS sudah berubah, muat ulang") from exc
        except Exception:
            self.db.rollback()
            raise

    def revise_krs(
        self,
        nim: str,
        dosen_pa_id: int,
        catatan: str,
        expected_version: Optional[int] = None,
        semester: Optional[int] = None,
    ) -> KRS:
        """Pengembalian KRS oleh Dosen PA untuk revisi (SUBMITTED -> REVISION).

        Catatan dari dosen PA wajib diisi. Dieksekusi dalam satu transaksi ACID.
        """
        if not catatan or not catatan.strip():
            raise ValidationInputError("Catatan revisi wajib diisi oleh dosen PA")

        catatan_bersih = catatan.strip()
        try:
            krs = self._krs_terkunci(nim, semester=semester)
            if krs.dosen_pa_id != dosen_pa_id:
                raise ForbiddenError("Anda bukan dosen PA mahasiswa ini")

            if expected_version is not None and krs.version != expected_version:
                raise KRSLockedError("KRS sudah berubah, muat ulang")

            krs.transition(KRSStatus.REVISION, Actor.DOSEN_PA)
            krs.catatan_revisi = catatan_bersih
            self.db.add(
                LogKRS(
                    krs_id=krs.id,
                    aksi="revise",
                    aktor=f"dosen_pa:{dosen_pa_id}",
                    catatan=catatan_bersih,
                )
            )
            self.db.add(
                Notifikasi(
                    nim=nim,
                    pesan=f"KRS Anda dikembalikan untuk revisi: {catatan_bersih}",
                )
            )
            self.db.commit()
            self.db.refresh(krs)
            return krs
        except StaleDataError as exc:
            self.db.rollback()
            raise KRSLockedError("KRS sudah berubah, muat ulang") from exc
        except Exception:
            self.db.rollback()
            raise
