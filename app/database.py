"""Konfigurasi koneksi database SQLAlchemy 2.0 untuk SEVIMA-Mini."""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

_DEFAULT_DB_PATH = (Path(__file__).resolve().parent.parent / "sevima_mini.db").as_posix()
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{_DEFAULT_DB_PATH}")


class Base(DeclarativeBase):
    """Base class deklaratif SQLAlchemy 2.0."""


def _build_connect_args(url: str) -> dict[str, Any]:
    if url.startswith("sqlite"):
        return {"check_same_thread": False}
    return {}


engine = create_engine(
    DATABASE_URL,
    connect_args=_build_connect_args(DATABASE_URL),
    future=True,
)


@event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection: Any, _connection_record: Any) -> None:
    """Aktifkan validasi FOREIGN KEY secara otomatis saat memakai SQLite."""
    module_name = type(dbapi_connection).__module__
    if "sqlite" in module_name:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=True,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """Dependency FastAPI untuk menyediakan session database per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
