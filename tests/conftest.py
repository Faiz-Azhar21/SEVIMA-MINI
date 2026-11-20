"""Pytest fixtures dengan database SQLite in-memory terisolasi dan dependency override."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.engine import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import JalurMasuk, ProgramStudi
from app.seed import seed_master_data

TEST_DATABASE_URL = "sqlite://"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)


@event.listens_for(test_engine, "connect")
def _enable_sqlite_fk(dbapi_connection: Any, _connection_record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine,
)


@pytest.fixture()
def db() -> Generator[Session, None, None]:
    """Menyiapkan tabel baru di SQLite in-memory untuk setiap test lalu membersihkannya."""
    Base.metadata.create_all(bind=test_engine)
    with TestingSessionLocal() as session:
        yield session
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture()
def client(db: Session) -> Generator[TestClient, None, None]:
    """TestClient FastAPI dengan override dependency `get_db` ke session test."""
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def master_data(db: Session) -> dict[str, Any]:
    """Mengisi data master ProgramStudi (001, 002, 003) & JalurMasuk (SNBP, SNBT, Mandiri)."""
    seed_master_data(db)
    prodi_ti = db.query(ProgramStudi).filter_by(kode="001").one()
    prodi_si = db.query(ProgramStudi).filter_by(kode="002").one()
    prodi_te = db.query(ProgramStudi).filter_by(kode="003").one()
    jalur_list = db.query(JalurMasuk).all()
    return {
        "prodi_ti": prodi_ti,
        "prodi_si": prodi_si,
        "prodi_te": prodi_te,
        "jalur_list": jalur_list,
    }


@pytest.fixture()
def prodi_ti(master_data: dict[str, Any]) -> ProgramStudi:
    """Fixture singkat untuk Program Studi Teknik Informatika (kode 001)."""
    return master_data["prodi_ti"]


def build_register_payload(
    email: str = "sinta@mail.com",
    phone: str = "081234567890",
    program_studi_id: int = 1,
    jalur_masuk: str = "SNBP",
    nama_lengkap: str = "Sinta Dewi",
    tanggal_lahir: str = "2006-05-14",
    alamat: str = "Jl. Merdeka No. 10, Surabaya",
) -> dict[str, Any]:
    """Helper pembuat payload JSON valid untuk endpoint POST /api/pmb/register."""
    return {
        "nama_lengkap": nama_lengkap,
        "email": email,
        "phone": phone,
        "tanggal_lahir": tanggal_lahir,
        "alamat": alamat,
        "program_studi_id": program_studi_id,
        "jalur_masuk": jalur_masuk,
    }


def daftar(
    client: TestClient,
    email: str,
    program_studi_id: int = 1,
    jalur_masuk: str = "SNBP",
    phone: str = "081234567890",
    nama_lengkap: str = "Calon Mahasiswa",
):
    """Helper mengirim POST /api/pmb/register dengan data valid."""
    payload = build_register_payload(
        email=email,
        phone=phone,
        program_studi_id=program_studi_id,
        jalur_masuk=jalur_masuk,
        nama_lengkap=nama_lengkap,
    )
    return client.post("/api/pmb/register", json=payload)
