"""Fixture pytest dengan database SQLite terisolasi per pengujian."""

from __future__ import annotations

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

# Pastikan scheduler background tidak menyala otomatis saat pytest berjalan
os.environ["ENABLE_SCHEDULER"] = "false"

from app import config, database  # noqa: E402
from app.database import Base, _create_db_engine, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Mahasiswa, PaymentMethod  # noqa: E402
from app.services import email_service  # noqa: E402


@pytest.fixture()
def test_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[Session, None, None]:
    db_file = tmp_path / "test_spp.db"
    receipts_dir = tmp_path / "receipts"
    receipts_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(email_service, "RECEIPTS_DIR", receipts_dir)
    monkeypatch.setattr(config, "RECEIPTS_DIR", receipts_dir)

    test_engine = _create_db_engine(f"sqlite:///{db_file.as_posix()}")
    Base.metadata.create_all(bind=test_engine)
    TestingSessionLocal = sessionmaker(
        bind=test_engine, autocommit=False, autoflush=False, expire_on_commit=False
    )

    monkeypatch.setattr(database, "engine", test_engine)
    monkeypatch.setattr(database, "SessionLocal", TestingSessionLocal)

    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        test_engine.dispose()


@pytest.fixture()
def seeded_basic_db(test_db: Session) -> Session:
    """Database minimal berisi payment_method dan mahasiswa aktif/non-aktif Teknik & Ekonomi."""
    methods = [
        PaymentMethod(code="VA_BCA", name="Virtual Account BCA", channel_type="gateway", admin_fee=0),
        PaymentMethod(code="TRANSFER_MANUAL", name="Transfer Bank Manual", channel_type="manual", admin_fee=0),
        PaymentMethod(code="QRIS", name="QRIS Kampus", channel_type="gateway", admin_fee=0),
    ]
    students = [
        Mahasiswa(
            nim="2401001",
            nama="Andi Teknik",
            email="andi@kampus.ac.id",
            program_studi="Teknik",
            angkatan=2024,
            status_aktif=True,
        ),
        Mahasiswa(
            nim="2402001",
            nama="Bunga Ekonomi",
            email="bunga@kampus.ac.id",
            program_studi="Ekonomi",
            angkatan=2024,
            status_aktif=True,
        ),
        Mahasiswa(
            nim="2402099",
            nama="Citra Cuti",
            email="citra@kampus.ac.id",
            program_studi="Ekonomi",
            angkatan=2023,
            status_aktif=False,
        ),
    ]
    test_db.add_all(methods + students)
    test_db.commit()
    return test_db


@pytest.fixture()
def client(seeded_basic_db: Session) -> Generator[TestClient, None, None]:
    def _override_get_db() -> Generator[Session, None, None]:
        yield seeded_basic_db

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as tc:
        yield tc
    app.dependency_overrides.clear()
