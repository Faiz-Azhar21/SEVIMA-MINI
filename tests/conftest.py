"""Fixture pytest bersama untuk database in-memory SQLite dan FastAPI TestClient."""

from __future__ import annotations

from collections.abc import Generator
from datetime import time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.jadwal import Dosen, Jadwal, Kelas, Ruangan
from app.models.krs import MataKuliah


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    """Session SQLite in-memory bersih per test dengan PRAGMA foreign_keys=ON."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=True,
        expire_on_commit=False,
    )
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """FastAPI TestClient yang mengarahkan get_db ke session test terisolasi."""

    def _override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def sample_entities(db_session: Session) -> dict[str, Any]:
    """Entitas dasar (ruangan, dosen, matakuliah, kelas) untuk pengujian service/API."""
    r_a101 = Ruangan(kode="A101", nama="Ruang A101", kapasitas=40)
    r_b201 = Ruangan(kode="B201", nama="Ruang B201", kapasitas=60)
    r_lab = Ruangan(kode="LAB1", nama="Lab Komputer 1", kapasitas=25)

    d1 = Dosen(nidn="0001018001", nama="Dr. Daniel")
    d2 = Dosen(nidn="0001018002", nama="Dr. Siti")

    mk1 = MataKuliah(kode_mk="IF203", nama="Basis Data", sks=3)
    mk2 = MataKuliah(kode_mk="IF302", nama="Statistika", sks=3)
    mk3 = MataKuliah(kode_mk="IF103", nama="Kalkulus I", sks=3)

    db_session.add_all([r_a101, r_b201, r_lab, d1, d2, mk1, mk2, mk3])
    db_session.flush()

    k_bd_a = Kelas(kode_mk="IF203", nama_kelas="Basis Data A", kuota=35, semester="20251")
    k_stat_b = Kelas(kode_mk="IF302", nama_kelas="Statistika B", kuota=40, semester="20251")
    k_besar = Kelas(kode_mk="IF103", nama_kelas="Kalkulus Besar", kuota=50, semester="20251")

    db_session.add_all([k_bd_a, k_stat_b, k_besar])
    db_session.commit()

    return {
        "ruangan": {"A101": r_a101, "B201": r_b201, "LAB1": r_lab},
        "dosen": [d1, d2],
        "matakuliah": [mk1, mk2, mk3],
        "kelas": {"bd_a": k_bd_a, "stat_b": k_stat_b, "besar": k_besar},
    }


@pytest.fixture()
def jadwal_a101(db_session: Session, sample_entities: dict[str, Any]) -> Jadwal:
    """Satu jadwal awal: Senin 08:00-09:40 di A101 dengan dosen 1."""
    j = Jadwal(
        kelas_id=sample_entities["kelas"]["bd_a"].id,
        hari=1,
        jam_mulai=time(8, 0),
        jam_selesai=time(9, 40),
        ruangan_kode="A101",
        dosen_id=sample_entities["dosen"][0].id,
    )
    db_session.add(j)
    db_session.commit()
    db_session.refresh(j)
    return j
