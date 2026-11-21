"""Konfigurasi SQLAlchemy 2 untuk SEVIMA-Mini."""

from __future__ import annotations

import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


DATABASE_URL = os.getenv("SEVIMA_DATABASE_URL", "sqlite:///./sevima_mini.db")


class Base(DeclarativeBase):
    """Declarative base untuk semua model ORM SEVIMA-Mini."""


def make_engine(url: str = DATABASE_URL):
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args, future=True)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db(target_engine=None) -> None:
    """Membuat seluruh tabel dari metadata ORM."""
    # Pastikan semua model sudah terdaftar pada Base.metadata
    from app.krs import models as _krs_models  # noqa: F401
    from app.scheduling import models as _sched_models  # noqa: F401

    Base.metadata.create_all(bind=target_engine or engine)


def get_db() -> Generator[Session, None, None]:
    """Dependency FastAPI untuk menyediakan sesi database per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
