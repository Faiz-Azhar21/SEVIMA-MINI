"""Fixture pytest untuk isolasi database SQLite (FK aktif) dan FastAPI TestClient."""

from __future__ import annotations

from collections.abc import Generator
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.database import Base, create_db_engine
from app.main import create_app
from app.ports.presensi import PresensiStub
from app.routers.deps import get_db, get_presensi_port
from app.seed import default_presensi_map, seed_dummy_data


@pytest.fixture()
def db_engine(tmp_path: Path) -> Generator[Engine, None, None]:
    db_file = tmp_path / "test_sevima.db"
    engine = create_db_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(db_engine: Engine) -> Generator[Session, None, None]:
    TestingSessionLocal = sessionmaker(
        bind=db_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    with TestingSessionLocal() as session:
        seed_dummy_data(session)
        yield session


@pytest.fixture()
def presensi_stub() -> PresensiStub:
    return PresensiStub(dict(default_presensi_map()))


@pytest.fixture()
def client(db_engine: Engine, presensi_stub: PresensiStub) -> Generator[TestClient, None, None]:
    TestingSessionLocal = sessionmaker(
        bind=db_engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    with TestingSessionLocal() as session:
        seed_dummy_data(session)

    app = create_app(init_db_on_startup=False)

    def _override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_presensi_port] = lambda: presensi_stub

    with TestClient(app) as test_client:
        yield test_client
