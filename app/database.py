"""Konfigurasi koneksi database SQLAlchemy 2.0 (SQLite lokal & kompatibel MySQL)."""

from __future__ import annotations

import os
from collections.abc import Generator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_DATABASE_URL = "sqlite:///./sevima_mini.db"


def get_database_url() -> str:
    """Ambil DATABASE_URL dari environment, default ke SQLite lokal."""
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    """Aktifkan enforcement FOREIGN KEY di SQLite untuk setiap koneksi."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_app_engine(database_url: str | None = None) -> Engine:
    """Buat SQLAlchemy Engine yang mendukung SQLite maupun MySQL."""
    url = database_url or get_database_url()
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args, future=True)

    if url.startswith("sqlite"):
        event.listen(engine, "connect", _enable_sqlite_foreign_keys)

    return engine


engine = create_app_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency untuk menyediakan session database per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
