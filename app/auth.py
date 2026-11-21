"""Autentikasi & kontrol akses berbasis peran (RBAC) sederhana untuk SEVIMA-Mini."""

from __future__ import annotations

from fastapi import Header, HTTPException, status


ADMIN_ROLES = {"admin", "admin_akademik"}


def require_admin(x_role: str | None = Header(default=None, alias="X-Role")) -> str:
    """Memastikan endpoint hanya dapat diakses oleh Admin Akademik.

    Header yang diterima: ``X-Role: admin_akademik`` (atau ``admin``).
    """
    if not x_role or x_role.strip().lower() not in ADMIN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Akses ditolak: hanya Admin Akademik yang diizinkan.",
        )
    return x_role.strip().lower()
