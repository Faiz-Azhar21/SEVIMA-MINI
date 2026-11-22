"""Konfigurasi koneksi SQLAlchemy, session, dan utilitas transaksi atomik."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import DATABASE_URL


class Base(DeclarativeBase):
    """Base declarative class untuk seluruh ORM model."""


def _create_db_engine(url: str) -> Engine:
    connect_args = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    eng = create_engine(url, connect_args=connect_args, future=True)

    if url.startswith("sqlite"):
        @event.listens_for(eng, "connect")
        def _set_sqlite_pragma(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            if ":memory:" not in url:
                cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    return eng


engine = _create_db_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)


def init_db(target_engine: Engine | None = None) -> None:
    """Inisialisasi seluruh tabel di database."""
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=target_engine or engine)


def get_db() -> Generator[Session, None, None]:
    """Dependency FastAPI untuk mendapatkan database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def atomic_transaction(db: Session) -> Generator[Session, None, None]:
    """Context manager untuk memastikan operasi database berjalan secara atomik.

    Mendukung nested transaction (SAVEPOINT) bila session sudah berada di dalam transaksi aktif.
    """
    if db.in_transaction():
        with db.begin_nested():
            yield db
        db.commit()
    else:
        with db.begin():
            yield db
