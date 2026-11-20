"""Fixtures pytest bersama untuk integration & API tests."""

from datetime import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.enums import JenisMK, KRSStatus
from app.main import app
from app.models import KRS, Matakuliah, Prerequisite, RiwayatNilai
from app.service import KRSManager


@pytest.fixture()
def db_session():
    """Database SQLite in-memory baru per test dengan Foreign Keys aktif."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=engine, future=True
    )
    session: Session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def seed_data(db_session: Session):
    """Data awal standar: mahasiswa Rina (semester 3, Dosen PA 101) & katalog MK."""
    courses = {
        "KAL1": Matakuliah(
            kode_mk="KAL1",
            kode_induk="KAL1",
            kelas="A",
            nama="Kalkulus I",
            sks=3,
            hari=1,
            jam_mulai=time(13, 0),
            jam_selesai=time(15, 0),
            jenis=JenisMK.WAJIB,
        ),
        "KAL2": Matakuliah(
            kode_mk="KAL2",
            kode_induk="KAL2",
            kelas="A",
            nama="Kalkulus II",
            sks=3,
            hari=2,
            jam_mulai=time(8, 0),
            jam_selesai=time(10, 0),
            jenis=JenisMK.WAJIB,
        ),
        "BD1": Matakuliah(
            kode_mk="BD1",
            kode_induk="BD1",
            kelas="A",
            nama="Basis Data",
            sks=3,
            hari=1,
            jam_mulai=time(8, 0),
            jam_selesai=time(10, 0),
            jenis=JenisMK.WAJIB,
        ),
        "PBO1": Matakuliah(
            kode_mk="PBO1",
            kode_induk="PBO1",
            kelas="A",
            nama="Pemrograman Berorientasi Objek",
            sks=3,
            hari=1,
            jam_mulai=time(8, 0),
            jam_selesai=time(10, 0),  # Sengaja bentrok dengan BD1
            jenis=JenisMK.WAJIB,
        ),
        "PBO1-B": Matakuliah(
            kode_mk="PBO1-B",
            kode_induk="PBO1",
            kelas="B",
            nama="Pemrograman Berorientasi Objek",
            sks=3,
            hari=3,
            jam_mulai=time(10, 0),
            jam_selesai=time(12, 0),  # Kelas paralel non-bentrok
            jenis=JenisMK.WAJIB,
        ),
        "ALGO": Matakuliah(
            kode_mk="ALGO",
            kode_induk="ALGO",
            kelas="A",
            nama="Algoritma & Struktur Data",
            sks=4,
            hari=2,
            jam_mulai=time(10, 0),  # Tepat setelah KAL2 (tidak bentrok)
            jam_selesai=time(12, 0),
            jenis=JenisMK.WAJIB,
        ),
        "JARKOM": Matakuliah(
            kode_mk="JARKOM",
            kode_induk="JARKOM",
            kelas="A",
            nama="Jaringan Komputer",
            sks=4,
            hari=4,
            jam_mulai=time(8, 0),
            jam_selesai=time(10, 0),
            jenis=JenisMK.WAJIB,
        ),
        "SO1": Matakuliah(
            kode_mk="SO1",
            kode_induk="SO1",
            kelas="A",
            nama="Sistem Operasi",
            sks=4,
            hari=4,
            jam_mulai=time(13, 0),
            jam_selesai=time(15, 0),
            jenis=JenisMK.WAJIB,
        ),
        "RPL1": Matakuliah(
            kode_mk="RPL1",
            kode_induk="RPL1",
            kelas="A",
            nama="Rekayasa Perangkat Lunak",
            sks=4,
            hari=5,
            jam_mulai=time(8, 0),
            jam_selesai=time(10, 0),
            jenis=JenisMK.WAJIB,
        ),
        "AI1": Matakuliah(
            kode_mk="AI1",
            kode_induk="AI1",
            kelas="A",
            nama="Kecerdasan Buatan",
            sks=3,
            hari=5,
            jam_mulai=time(13, 0),
            jam_selesai=time(15, 0),
            jenis=JenisMK.PILIHAN,
        ),
        "GAME1": Matakuliah(
            kode_mk="GAME1",
            kode_induk="GAME1",
            kelas="A",
            nama="Pengembangan Game",
            sks=3,
            hari=6,
            jam_mulai=time(8, 0),
            jam_selesai=time(10, 0),
            jenis=JenisMK.PILIHAN,
        ),
        "ML1": Matakuliah(
            kode_mk="ML1",
            kode_induk="ML1",
            kelas="A",
            nama="Machine Learning",
            sks=3,
            hari=1,
            jam_mulai=time(8, 0),
            jam_selesai=time(10, 0),  # Bentrok dengan BD1 (WAJIB)
            jenis=JenisMK.PILIHAN,
        ),
    }

    db_session.add_all(courses.values())
    db_session.flush()

    # KAL2 membutuhkan prasyarat KAL1 dengan nilai minimal C
    db_session.add(
        Prerequisite(kode_mk="KAL2", prasyarat_kode_mk="KAL1", nilai_minimal="C")
    )

    krs_rina = KRS(
        nim="2026001",
        semester=3,
        dosen_pa_id=101,
        status=KRSStatus.DRAFT,
    )
    krs_budi = KRS(
        nim="2026002",
        semester=3,
        dosen_pa_id=102,
        status=KRSStatus.DRAFT,
    )
    db_session.add_all([krs_rina, krs_budi])

    # Budi sudah lulus KAL1 dengan nilai B di semester 1
    db_session.add(
        RiwayatNilai(nim="2026002", kode_mk="KAL1", semester=1, nilai_huruf="B")
    )
    db_session.commit()

    return {
        "rina": krs_rina,
        "budi": krs_budi,
        "courses": courses,
    }


@pytest.fixture()
def manager(db_session: Session, seed_data) -> KRSManager:
    return KRSManager(db_session)


@pytest.fixture()
def client(db_session: Session, seed_data, monkeypatch):
    """FastAPI TestClient yang diarahkan ke DB SQLite in-memory per test."""
    import app.main as main_module

    def _override_get_db():
        yield db_session

    # Hindari pembuatan file sevima_krs.db saat lifespan berjalan di mode test
    monkeypatch.setattr(main_module, "init_db", lambda: None)
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
