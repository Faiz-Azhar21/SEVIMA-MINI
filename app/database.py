"""Konfigurasi koneksi database, Base ORM, dan Dependency Injection sesi DB."""

from __future__ import annotations

import os
from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./pmb.db")


class Base(DeclarativeBase):
    """Base class deklaratif SQLAlchemy 2.0 untuk seluruh model ORM."""


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


def _configure_sqlite_pragma(dbapi_connection: Any, _connection_record: Any) -> None:
    """Aktifkan enforcement FOREIGN KEY pada setiap koneksi SQLite."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def create_app_engine(url: str = DATABASE_URL, **kwargs: Any) -> Engine:
    """Membuat SQLAlchemy Engine sesuai dialect (SQLite/MySQL)."""
    connect_args = dict(kwargs.pop("connect_args", {}))
    if _is_sqlite(url):
        connect_args.setdefault("check_same_thread", False)

    eng = create_engine(url, connect_args=connect_args, **kwargs)
    if _is_sqlite(url):
        event.listen(eng, "connect", _configure_sqlite_pragma)
    return eng


engine = create_app_engine(DATABASE_URL)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db() -> Generator[Session, None, None]:
    """Dependency Injection FastAPI untuk menyediakan sesi database per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
