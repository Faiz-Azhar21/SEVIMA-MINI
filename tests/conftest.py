"""Fixture bersama pytest menggunakan SQLite in-memory (StaticPool) & FastAPI TestClient."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.krs.invalidator import KRSInvalidator
from app.main import app, wire_observers
from app.scheduling.outbox import OutboxDispatcher
from app.scheduling.router import get_service, runtime_state
from app.scheduling.service import SchedulingService
from app.seed import seed_demo_data


@pytest.fixture()
def session_factory():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    yield factory
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def db(session_factory) -> Session:
    session = session_factory()
    seed_demo_data(session)
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def log_sink() -> list[dict[str, Any]]:
    return []


@pytest.fixture()
def service_bundle(db: Session, session_factory, log_sink):
    subject, idem_store = wire_observers(session_factory, log_sink=log_sink)
    dispatcher = OutboxDispatcher(db=db, subject=subject)
    svc = SchedulingService(db=db, krs=KRSInvalidator(db), dispatcher=dispatcher)
    return {
        "svc": svc,
        "db": db,
        "subject": subject,
        "dispatcher": dispatcher,
        "idem_store": idem_store,
        "logs": log_sink,
    }


@pytest.fixture()
def client(session_factory):
    # Seed database in-memory
    seed_db = session_factory()
    try:
        seed_demo_data(seed_db)
    finally:
        seed_db.close()

    logs: list[dict[str, Any]] = []
    subject, _ = wire_observers(session_factory, log_sink=logs)

    old_subject = runtime_state.subject
    old_logs = runtime_state.notification_logs
    runtime_state.subject = subject
    runtime_state.notification_logs = logs

    def _override_db():
        s = session_factory()
        try:
            yield s
        finally:
            s.close()

    def _override_service():
        s = session_factory()
        try:
            disp = OutboxDispatcher(db=s, subject=runtime_state.subject)
            yield SchedulingService(db=s, krs=KRSInvalidator(s), dispatcher=disp)
        finally:
            s.close()

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_service] = _override_service

    with TestClient(app) as tc:
        # Pastikan state runtime memakai subject in-memory test (bukan lifespan default DB)
        runtime_state.subject = subject
        runtime_state.notification_logs = logs
        yield tc

    app.dependency_overrides.clear()
    runtime_state.subject = old_subject
    runtime_state.notification_logs = old_logs
