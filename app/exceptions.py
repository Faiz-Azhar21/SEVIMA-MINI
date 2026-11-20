"""Hierarki exception berbasis OOP untuk Modul KRS.

Menggunakan polimorfisme atribut `status_code` sehingga lapisan service tetap
independen dari framework HTTP, dan FastAPI cukup memiliki satu exception handler
untuk `KRSError` dan seluruh turunannya.
"""


class KRSError(Exception):
    """Exception dasar untuk pelanggaran aturan bisnis KRS (HTTP 400)."""

    status_code: int = 400


class ForbiddenError(KRSError):
    """Aktor atau kepemilikan tidak berwenang melakukan aksi (HTTP 403)."""

    status_code: int = 403


class NotFoundError(KRSError):
    """Data mahasiswa/KRS/mata kuliah tidak ditemukan (HTTP 404)."""

    status_code: int = 404


class TransitionError(KRSError):
    """Perpindahan status KRS melanggar aturan state machine (HTTP 409)."""

    status_code: int = 409


class KRSLockedError(KRSError):
    """KRS sedang terkunci (status SUBMITTED/APPROVED) atau versi stale (HTTP 409)."""

    status_code: int = 409


class ValidationInputError(KRSError):
    """Input wajib tidak valid, misalnya catatan revisi kosong (HTTP 422)."""

    status_code: int = 422
