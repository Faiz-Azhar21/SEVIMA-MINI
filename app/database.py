"""Inisialisasi koneksi database SQLAlchemy."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


def create_db_engine(database_url: str | None = None):
    url = database_url or settings.DATABASE_URL
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args, future=True)


engine = create_db_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)


class Base(DeclarativeBase):
    """Base declarative class untuk semua model ORM."""


def init_db(target_engine=None) -> None:
    """Membuat seluruh tabel database jika belum ada."""
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=target_engine or engine)


def get_db() -> Generator[Session, None, None]:
    """Dependency FastAPI untuk menyediakan session database per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
