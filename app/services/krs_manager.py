"""KRSManager Service — satu pintu untuk seluruh operasi bisnis KRS.

Patuh Single Responsibility Principle:
- Mengatur alur transaksi, penguncian baris (row lock), penjagaan status, dan validasi.
- Tidak mengenal detail HTTP maupun magic number batas SKS.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models.krs import KRS, KRSDetail, KRSStatus, MataKuliah
from app.models.pmb import CalonMahasiswa
from app.validators.base import KRSContext, ValidationResult, Validator, build_chain

EDITABLE = {KRSStatus.DRAFT, KRSStatus.REVISION}
DEFAULT_SEMESTER = "20251"


class KRSError(Exception):
    """Base domain exception untuk pelanggaran aturan pada Modul KRS."""


class KRSNotFoundError(KRSError):
    """Entitas yang diminta (mahasiswa ber-NIM, mata kuliah, atau item KRS) tidak ditemukan."""


class KRSStateError(KRSError):
    """Operasi ditolak karena status KRS saat ini tidak mengizinkan perubahan."""


class KRSValidationError(KRSError):
    """Pelanggaran aturan bisnis dari rantai validator."""


class KRSManager:
    """Service layer untuk mengelola pengisian dan validasi KRS."""

    def __init__(
        self,
        db: Session,
        validators: list[Validator],
        semester: str | None = None,
    ) -> None:
        self.db = db
        self.semester = semester or DEFAULT_SEMESTER
        self.validators = list(validators)
        self.chain = build_chain(self.validators)

    def _pastikan_mahasiswa_ber_nim(self, nim: str) -> CalonMahasiswa:
        """Pastikan mahasiswa sudah disetujui di Modul PMB dan memiliki NIM valid."""
        mhs = self.db.scalar(
            select(CalonMahasiswa).where(CalonMahasiswa.nim == nim)
        )
        if mhs is None:
            raise KRSNotFoundError(
                f"Mahasiswa dengan NIM {nim} tidak ditemukan atau belum disetujui PMB"
            )
        return mhs

    def _krs_terkunci(self, nim: str, buat_jika_belum_ada: bool = True) -> KRS | None:
        """Ambil baris KRS mahasiswa pada semester aktif dengan row lock (`FOR UPDATE`).

        Menggunakan `selectinload(KRS.details).joinedload(KRSDetail.matakuliah)`
        untuk mencegah masalah query N+1 sekaligus tetap kompatibel dengan `FOR UPDATE`.
        """
        self._pastikan_mahasiswa_ber_nim(nim)

        stmt = (
            select(KRS)
            .where(KRS.nim == nim, KRS.semester == self.semester)
            .options(selectinload(KRS.details).joinedload(KRSDetail.matakuliah))
            .with_for_update()
        )
        krs = self.db.scalar(stmt)
        if krs is None and buat_jika_belum_ada:
            krs = KRS(nim=nim, semester=self.semester, status=KRSStatus.DRAFT)
            self.db.add(krs)
            self.db.flush()
            # Muat ulang dengan row lock agar aman terhadap transaksi konkuren
            krs = self.db.scalar(stmt)
        return krs

    def get_krs(self, nim: str) -> KRS:
        """Ambil KRS mahasiswa untuk semester aktif (buat DRAFT kosong jika belum ada)."""
        krs = self._krs_terkunci(nim, buat_jika_belum_ada=True)
        assert krs is not None
        self.db.commit()
        return krs

    def add_course(self, nim: str, kode_mk: str) -> KRSDetail:
        """Tambahkan mata kuliah ke KRS dalam satu transaksi atomik (fail-fast)."""
        krs = self._krs_terkunci(nim, buat_jika_belum_ada=True)
        assert krs is not None

        if krs.status not in EDITABLE:
            self.db.rollback()
            raise KRSStateError(f"KRS ({krs.status.value}) tidak bisa diubah")

        mk = self.db.get(MataKuliah, kode_mk)
        if mk is None:
            self.db.rollback()
            raise KRSNotFoundError(f"Mata kuliah {kode_mk} tidak ditemukan")

        ctx = KRSContext(nim, krs.semester, list(krs.details), mk, self.db)
        hasil = self.chain.validate(ctx)
        if not hasil.ok:
            self.db.rollback()
            raise KRSValidationError(hasil.message)

        detail = KRSDetail(matakuliah=mk)
        krs.details.append(detail)
        try:
            self.db.commit()  # Satu transaksi — commit sekali di akhir
        except IntegrityError as exc:
            self.db.rollback()
            raise KRSValidationError(
                f"Sudah ada di KRS: {mk.nama} (dicegah oleh constraint database)"
            ) from exc

        return detail

    def remove_course(self, nim: str, kode_mk: str) -> None:
        """Hapus mata kuliah dari KRS (hanya saat status DRAFT atau REVISION)."""
        krs = self._krs_terkunci(nim, buat_jika_belum_ada=False)
        if krs is None:
            raise KRSNotFoundError(
                f"KRS untuk NIM {nim} pada semester {self.semester} belum ada"
            )

        if krs.status not in EDITABLE:
            self.db.rollback()
            raise KRSStateError(f"KRS ({krs.status.value}) tidak bisa diubah")

        detail = next((d for d in krs.details if d.kode_mk == kode_mk), None)
        if detail is None:
            self.db.rollback()
            raise KRSNotFoundError(f"{kode_mk} tidak ada di KRS")

        krs.details.remove(detail)  # delete-orphan akan menghapus baris di DB
        self.db.commit()

    def validate_krs(self, nim: str) -> list[ValidationResult]:
        """Periksa seluruh aturan pada KRS dan kumpulkan SEMUA pelanggaran (collect-all).

        Setiap validator dipanggil lewat `.check(ctx)` secara langsung tanpa
        terhenti oleh kegagalan pertama sehingga mahasiswa dapat melihat semua
        masalah sekaligus dalam satu layar sebelum submit.
        """
        krs = self._krs_terkunci(nim, buat_jika_belum_ada=False)
        if krs is None:
            return []

        gagal: dict[str, ValidationResult] = {}
        for d in krs.details:
            lain = [x for x in krs.details if x is not d]
            ctx = KRSContext(nim, krs.semester, lain, d.matakuliah, self.db)
            for v in self.validators:  # check langsung, tanpa rantai
                r = v.check(ctx)
                if not r.ok:
                    dedup_key = self._dedup_key(r.message)
                    gagal.setdefault(dedup_key, r)
        return list(gagal.values())

    @staticmethod
    def _dedup_key(message: str) -> str:
        """Normalisasi kunci deduplikasi agar bentrok simetris (A vs B dan B vs A)
        hanya dilaporkan sekali pada `validate_krs()`.
        """
        prefix = "Jadwal bentrok: "
        if message.startswith(prefix) and " dengan " in message:
            bagian = message[len(prefix) :].split(" dengan ", maxsplit=1)
            return prefix + " | ".join(sorted(bagian))
        return message

    # --- Minggu 6: State Machine (stub kontrak interface sesuai dokumen tugas) ---
    def submit_krs(self, nim: str) -> KRS:
        """Ajukan KRS (DRAFT/REVISION -> SUBMITTED). Diimplementasikan di Minggu 6."""
        raise NotImplementedError(
            "submit_krs beserta State Machine diimplementasikan pada Minggu 6"
        )

    def approve_krs(self, nim: str, dosen_pa_id: int) -> KRS:
        """Setujui KRS oleh Dosen PA (SUBMITTED -> APPROVED). Diimplementasikan di Minggu 6."""
        raise NotImplementedError(
            "approve_krs beserta State Machine diimplementasikan pada Minggu 6"
        )
