"""SchedulingService: CRUD jadwal dengan deteksi bentrok, capacity check, dan row lock."""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.jadwal import Dosen, Jadwal, Kelas, Ruangan
from app.models.krs import KRSDetail
from app.schemas.jadwal import JadwalIn
from app.services.conflict import Conflict, detect_schedule_conflict
from app.services.exceptions import (
    CapacityError,
    NotFoundError,
    ScheduleConflictError,
)


def cek_kapasitas(db: Session, kelas_id: int, ruangan_kode: str) -> None:
    """Pastikan peserta kelas (max(kuota, terdaftar)) <= kapasitas ruangan.

    Di awal semester saat belum ada mahasiswa mengisi KRS (terdaftar = 0),
    nilai kelas.kuota tetap mencegah kelas besar dimasukkan ke ruang sempit.
    """
    ruang = db.get(Ruangan, ruangan_kode)
    kelas = db.get(Kelas, kelas_id)
    if ruang is None or kelas is None:
        raise NotFoundError("Ruangan atau kelas tidak ditemukan")

    terdaftar = (
        db.scalar(
            select(func.count())
            .select_from(KRSDetail)
            .where(KRSDetail.kelas_id == kelas_id)
        )
        or 0
    )
    peserta = max(kelas.kuota, terdaftar)
    if peserta > ruang.kapasitas:
        raise CapacityError(
            f"Ruang {ruang.kode} berkapasitas {ruang.kapasitas}, "
            f"kelas {kelas.nama_kelas} butuh {peserta} kursi"
        )


class SchedulingService:
    """Layanan domain penjadwalan yang terpisah penuh dari lapisan HTTP."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, data: JadwalIn) -> Jadwal:
        """Buat jadwal baru setelah lolos pemeriksaan bentrok dan kapasitas."""
        return self._simpan(Jadwal(), data)

    def update(self, jadwal_id: int, data: JadwalIn) -> Jadwal:
        """Perbarui jadwal yang ada; diri sendiri dikecualikan dari deteksi bentrok."""
        jadwal = self.db.get(Jadwal, jadwal_id)
        if jadwal is None:
            raise NotFoundError(f"Jadwal {jadwal_id} tidak ditemukan")
        return self._simpan(jadwal, data)

    def delete(self, jadwal_id: int) -> None:
        """Hapus jadwal dalam satu transaksi atomik."""
        try:
            jadwal = self.db.get(Jadwal, jadwal_id)
            if jadwal is None:
                raise NotFoundError(f"Jadwal {jadwal_id} tidak ditemukan")
            self.db.delete(jadwal)
            # Minggu 8: subject.notify("SCHEDULE_DELETED", jadwal_data)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def list_all(self) -> list[Jadwal]:
        """Kembalikan seluruh jadwal terurut berdasarkan hari dan jam_mulai."""
        stmt = select(Jadwal).order_by(Jadwal.hari, Jadwal.jam_mulai, Jadwal.id)
        return list(self.db.scalars(stmt).all())

    def list_conflicts(self) -> list[Conflict]:
        """Deteksi seluruh bentrok yang terlanjur ada di DB (mis. data hasil impor)."""
        semua = list(self.db.scalars(select(Jadwal)).all())
        return detect_schedule_conflict(semua)

    def _simpan(self, jadwal: Jadwal, data: JadwalIn) -> Jadwal:
        """Alur atomik bersama untuk create dan update: periksa dulu, baru simpan."""
        try:
            self._kunci(data.ruangan_kode, data.dosen_id)
            if self.db.get(Kelas, data.kelas_id) is None:
                raise NotFoundError(f"Kelas {data.kelas_id} tidak ditemukan")

            konflik = self._bentrok_di_db(data, abaikan_id=jadwal.id)
            if konflik:
                raise ScheduleConflictError(konflik)

            cek_kapasitas(self.db, data.kelas_id, data.ruangan_kode)

            for kolom, nilai in data.model_dump().items():
                setattr(jadwal, kolom, nilai)

            # Ditambahkan paling akhir agar SQLAlchemy autoflush tidak memicu
            # bentrok terhadap dirinya sendiri sebelum validasi selesai.
            self.db.add(jadwal)
            # Minggu 8: subject.notify("SCHEDULE_CHANGED", jadwal_data)
            self.db.commit()
            self.db.refresh(jadwal)
        except Exception:
            self.db.rollback()
            raise
        return jadwal

    def _kunci(self, ruangan_kode: str, dosen_id: int) -> None:
        """Pessimistic row lock dengan urutan tetap (Ruangan -> Dosen) anti-deadlock.

        Catatan: SQLite mengabaikan SELECT ... FOR UPDATE; pembuktian konkurensi
        harus dijalankan pada MySQL (InnoDB).
        """
        ruang = self.db.scalar(
            select(Ruangan).where(Ruangan.kode == ruangan_kode).with_for_update()
        )
        if ruang is None:
            raise NotFoundError(f"Ruangan {ruangan_kode} tidak ditemukan")

        dosen = self.db.scalar(
            select(Dosen).where(Dosen.id == dosen_id).with_for_update()
        )
        if dosen is None:
            raise NotFoundError(f"Dosen {dosen_id} tidak ditemukan")

    def _bentrok_di_db(
        self,
        data: JadwalIn,
        abaikan_id: int | None = None,
    ) -> list[Conflict]:
        """Cari bentrok langsung di SQL memakai index (hari, ruangan_kode) & (hari, dosen_id)."""
        stmt = select(Jadwal).where(
            Jadwal.hari == data.hari,
            Jadwal.jam_mulai < data.jam_selesai,
            Jadwal.jam_selesai > data.jam_mulai,
            or_(
                Jadwal.ruangan_kode == data.ruangan_kode,
                Jadwal.dosen_id == data.dosen_id,
            ),
        )
        if abaikan_id is not None:
            stmt = stmt.where(Jadwal.id != abaikan_id)

        hasil: list[Conflict] = []
        for lama in self.db.scalars(stmt):
            if lama.ruangan_kode == data.ruangan_kode:
                hasil.append(Conflict("room_conflict", (lama.id,)))
            if lama.dosen_id == data.dosen_id:
                hasil.append(Conflict("lecturer_conflict", (lama.id,)))
        return hasil
