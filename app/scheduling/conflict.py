"""Algoritma deteksi bentrok 3 dimensi (Interval Tree + pengelompokan) & capacity check.

Memenuhi Deliverable 1 (35%) dan Step 1:
- Interval setengah terbuka ``[jam_mulai, jam_selesai)`` sehingga jadwal selesai 10:00
  tidak bentrok dengan jadwal mulai 10:00.
- Deteksi bentrok 3 dimensi: ``room_conflict``, ``lecturer_conflict``, dan ``time_overlap``.
- Optimasi overlap check menggunakan AVL-balanced Augmented Interval Tree ``O(log n + k)``.
- Capacity check: ``max(kelas.kuota, mahasiswa_enrolled) <= ruangan.kapasitas``.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import time
from typing import Any, Generic, Sequence, TypeVar

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.krs.models import KRSDetail
from app.scheduling.models import Jadwal, Kelas, Ruangan

T = TypeVar("T")


@dataclass(frozen=True)
class Conflict:
    """Representasi bentrok antara dua jadwal."""

    type: str  # 'room_conflict' | 'lecturer_conflict' | 'time_overlap'
    affected: tuple[int, int]
    detail: str = ""


class ScheduleConflictError(Exception):
    """Dilempar saat operasi create/update jadwal melanggar constraint bentrok (HTTP 409)."""

    def __init__(self, conflicts: list[Conflict], message: str | None = None) -> None:
        self.conflicts = conflicts
        if message is None:
            ringkasan = "; ".join(f"{c.type} {c.affected}" for c in conflicts)
            message = f"Bentrok jadwal terdeteksi: {ringkasan}"
        super().__init__(message)


class CapacityExceededError(Exception):
    """Dilempar saat peserta kelas melebihi kapasitas ruangan (HTTP 409)."""

    def __init__(self, peserta: int, kapasitas: int, ruangan_kode: str) -> None:
        self.peserta = peserta
        self.kapasitas = kapasitas
        self.ruangan_kode = ruangan_kode
        super().__init__(
            f"Kapasitas ruangan {ruangan_kode} ({kapasitas}) tidak cukup untuk {peserta} peserta."
        )


class _IntervalNode(Generic[T]):
    __slots__ = ("start", "end", "payload", "max_end", "height", "left", "right")

    def __init__(self, start: int, end: int, payload: T) -> None:
        self.start = start
        self.end = end
        self.payload = payload
        self.max_end = end
        self.height = 1
        self.left: _IntervalNode[T] | None = None
        self.right: _IntervalNode[T] | None = None


class IntervalTree(Generic[T]):
    """AVL-balanced Augmented Interval Tree untuk interval setengah terbuka ``[start, end)``."""

    def __init__(self) -> None:
        self._root: _IntervalNode[T] | None = None

    @staticmethod
    def _h(node: _IntervalNode[T] | None) -> int:
        return node.height if node else 0

    @staticmethod
    def _update(node: _IntervalNode[T]) -> None:
        node.height = 1 + max(IntervalTree._h(node.left), IntervalTree._h(node.right))
        max_end = node.end
        if node.left and node.left.max_end > max_end:
            max_end = node.left.max_end
        if node.right and node.right.max_end > max_end:
            max_end = node.right.max_end
        node.max_end = max_end

    @classmethod
    def _rotate_right(cls, y: _IntervalNode[T]) -> _IntervalNode[T]:
        assert y.left is not None
        x = y.left
        t2 = x.right
        x.right = y
        y.left = t2
        cls._update(y)
        cls._update(x)
        return x

    @classmethod
    def _rotate_left(cls, x: _IntervalNode[T]) -> _IntervalNode[T]:
        assert x.right is not None
        y = x.right
        t2 = y.left
        y.left = x
        x.right = t2
        cls._update(x)
        cls._update(y)
        return y

    @classmethod
    def _balance(cls, node: _IntervalNode[T]) -> _IntervalNode[T]:
        cls._update(node)
        bf = cls._h(node.left) - cls._h(node.right)
        if bf > 1:
            assert node.left is not None
            if cls._h(node.left.right) > cls._h(node.left.left):
                node.left = cls._rotate_left(node.left)
            return cls._rotate_right(node)
        if bf < -1:
            assert node.right is not None
            if cls._h(node.right.left) > cls._h(node.right.right):
                node.right = cls._rotate_right(node.right)
            return cls._rotate_left(node)
        return node

    def _insert(self, node: _IntervalNode[T] | None, start: int, end: int, payload: T) -> _IntervalNode[T]:
        if node is None:
            return _IntervalNode(start, end, payload)
        if (start, end) < (node.start, node.end):
            node.left = self._insert(node.left, start, end, payload)
        else:
            node.right = self._insert(node.right, start, end, payload)
        return self._balance(node)

    def insert(self, start: int, end: int, payload: T) -> None:
        self._root = self._insert(self._root, start, end, payload)

    def _query(self, node: _IntervalNode[T] | None, start: int, end: int, out: list[T]) -> None:
        if node is None or node.max_end <= start:
            return
        # Interval setengah terbuka [start, end) overlap dengan [node.start, node.end)
        # jika dan hanya jika start < node.end dan node.start < end
        if node.left is not None and node.left.max_end > start:
            self._query(node.left, start, end, out)
        if start < node.end and node.start < end:
            out.append(node.payload)
        if node.right is not None and node.start < end:
            self._query(node.right, start, end, out)

    def query_overlaps(self, start: int, end: int) -> list[T]:
        out: list[T] = []
        self._query(self._root, start, end, out)
        return out


def _to_minutes(t: time | str) -> int:
    if isinstance(t, str):
        parts = t.split(":")
        return int(parts[0]) * 60 + int(parts[1])
    return t.hour * 60 + t.minute


def _attr(obj: Any, *names: str) -> Any:
    for name in names:
        if isinstance(obj, dict) and name in obj:
            return obj[name]
        if hasattr(obj, name):
            return getattr(obj, name)
    return None


def _scan_group(items: list[Any], conflict_type: str, label: str) -> list[Conflict]:
    """Menyapu kelompok jadwal dengan IntervalTree untuk menemukan semua pasangan overlap."""
    ordered = sorted(
        items,
        key=lambda j: (
            _to_minutes(_attr(j, "jam_mulai")),
            _to_minutes(_attr(j, "jam_selesai")),
            _attr(j, "id") if _attr(j, "id") is not None else 0,
        ),
    )
    tree: IntervalTree[Any] = IntervalTree()
    conflicts: list[Conflict] = []
    for item in ordered:
        start = _to_minutes(_attr(item, "jam_mulai"))
        end = _to_minutes(_attr(item, "jam_selesai"))
        item_id = int(_attr(item, "id"))
        overlaps = tree.query_overlaps(start, end)
        for prev in overlaps:
            prev_id = int(_attr(prev, "id"))
            pair = (min(prev_id, item_id), max(prev_id, item_id))
            conflicts.append(
                Conflict(
                    type=conflict_type,
                    affected=pair,
                    detail=f"Bentrok {label} pada hari {_attr(item, 'hari')}",
                )
            )
        tree.insert(start, end, item)
    return conflicts


def detect_schedule_conflict(schedules: Sequence[Any]) -> list[Conflict]:
    """Mendeteksi bentrok jadwal 3 dimensi menggunakan pengelompokan + Interval Tree.

    Jenis konflik yang dihasilkan:
    - ``room_conflict``: hari sama, jam overlap, ruangan sama.
    - ``lecturer_conflict``: hari sama, jam overlap, dosen sama.
    - ``time_overlap``: hari sama, jam overlap pada kelas yang sama (di luar room/lecturer).
    """
    by_room: dict[tuple[Any, Any], list[Any]] = defaultdict(list)
    by_lecturer: dict[tuple[Any, Any], list[Any]] = defaultdict(list)
    by_class: dict[tuple[Any, Any], list[Any]] = defaultdict(list)

    for idx, j in enumerate(schedules):
        # Pastikan jadwal berbasis dict tanpa id tetap memiliki pengenal
        if isinstance(j, dict) and "id" not in j:
            j = {**j, "id": idx}
        hari = _attr(j, "hari")
        ruangan = _attr(j, "ruangan_kode", "ruangan")
        dosen = _attr(j, "dosen_id", "dosen")
        kelas = _attr(j, "kelas_id", "kelas")

        if ruangan is not None:
            by_room[(hari, ruangan)].append(j)
        if dosen is not None:
            by_lecturer[(hari, dosen)].append(j)
        if kelas is not None:
            by_class[(hari, kelas)].append(j)

    conflicts: list[Conflict] = []
    seen_pairs: set[tuple[int, int]] = set()

    for (_, ruangan), items in by_room.items():
        if len(items) > 1:
            for c in _scan_group(items, "room_conflict", f"ruangan {ruangan}"):
                conflicts.append(c)
                seen_pairs.add(c.affected)

    for (_, dosen), items in by_lecturer.items():
        if len(items) > 1:
            for c in _scan_group(items, "lecturer_conflict", f"dosen {dosen}"):
                conflicts.append(c)
                seen_pairs.add(c.affected)

    for (_, kelas), items in by_class.items():
        if len(items) > 1:
            for c in _scan_group(items, "time_overlap", f"kelas {kelas}"):
                if c.affected not in seen_pairs:
                    conflicts.append(c)

    return conflicts


def hitung_peserta_kelas(db: Session, kelas_id: int) -> tuple[int, int]:
    """Mengembalikan ``(peserta_efektif, jumlah_terdaftar)`` untuk kelas terkait.

    Sesuai Slide 14: ``peserta = max(kuota, terdaftar)`` agar ruangan aman baik terhadap
    rencana kuota kelas maupun jumlah mahasiswa yang benar-benar enrolled.
    """
    kelas = db.get(Kelas, kelas_id)
    if kelas is None:
        raise ValueError(f"Kelas {kelas_id} tidak ditemukan")
    terdaftar = (
        db.scalar(
            select(func.count(KRSDetail.id)).where(KRSDetail.kelas_id == kelas_id)
        )
        or 0
    )
    return max(kelas.kuota, int(terdaftar)), int(terdaftar)


def cek_kapasitas(db: Session, kelas_id: int, ruangan_kode: str) -> None:
    """Memastikan kapasitas ruangan mencukupi untuk peserta kelas."""
    ruangan = db.get(Ruangan, ruangan_kode)
    if ruangan is None:
        raise ValueError(f"Ruangan {ruangan_kode} tidak ditemukan")
    peserta, _ = hitung_peserta_kelas(db, kelas_id)
    if peserta > ruangan.kapasitas:
        raise CapacityExceededError(peserta, ruangan.kapasitas, ruangan_kode)
