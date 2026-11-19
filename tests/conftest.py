import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.database import Base, get_db
from app.models.program_studi import ProgramStudi
from app.models.jalur_masuk import JalurMasuk
from app.main import app

@pytest.fixture(scope="function")
def test_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()

    # Seed data program studi
    prodi_list = [
        ProgramStudi(id=1, kode="001", nama="Teknik Informatika", fakultas="Fakultas Ilmu Komputer"),
        ProgramStudi(id=2, kode="002", nama="Sistem Informasi", fakultas="Fakultas Ilmu Komputer"),
        ProgramStudi(id=3, kode="003", nama="Teknik Komputer", fakultas="Fakultas Teknik"),
    ]
    db.add_all(prodi_list)

    # Seed data jalur masuk
    jalur_list = [
        JalurMasuk(id=1, kode="SNBP", nama="Seleksi Nasional Berdasarkan Prestasi", keterangan="Jalur rapor"),
        JalurMasuk(id=2, kode="SNBT", nama="Seleksi Nasional Berdasarkan Tes", keterangan="Jalur UTBK"),
        JalurMasuk(id=3, kode="Mandiri", nama="Seleksi Mandiri", keterangan="Jalur ujian mandiri"),
    ]
    db.add_all(jalur_list)
    db.commit()
    db.close()

    yield engine

    Base.metadata.drop_all(bind=engine)

@pytest.fixture(scope="function")
def test_db(test_engine):
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture(scope="function")
def client(test_engine):
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
