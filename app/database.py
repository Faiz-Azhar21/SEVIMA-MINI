"""Konfigurasi koneksi database SQLAlchemy 2.x untuk SEVIMA-Mini."""

from __future__ import annotations

import os
from collections.abc import Generator
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DEFAULT_DATABASE_URL = "sqlite:///./sevima_mini.db"


class Base(DeclarativeBase):
    """Base class untuk seluruh model ORM SEVIMA-Mini."""


def _enable_sqlite_foreign_keys(dbapi_connection: Any, _connection_record: Any) -> None:
    """Aktifkan PRAGMA foreign_keys=ON pada setiap koneksi SQLite agar FK ditegakkan DB."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_db_engine(database_url: str | None = None) -> Engine:
    """Buat SQLAlchemy Engine dengan enforcement Foreign Key untuk SQLite."""
    url = database_url or os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, connect_args=connect_args, future=True)
    if url.startswith("sqlite"):
        event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    return engine


engine = create_db_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_session() -> Generator[Session, None, None]:
    """Generator session database per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
