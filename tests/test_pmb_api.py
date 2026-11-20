"""Integration tests lengkap untuk REST API modul PMB (Step 4 & Deliverable Unit Tests)."""

from __future__ import annotations

import re
from datetime import date, timedelta
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import CalonMahasiswa, ProgramStudi, StatusPMB
from tests.conftest import build_register_payload, daftar


# ---------------------------------------------------------------------------
# 5 Test Wajib dari Step 4 Dokumen Tugas
# ---------------------------------------------------------------------------


def test_register_success(client: TestClient, prodi_ti: ProgramStudi) -> None:
    """Data registrasi valid mengembalikan HTTP 201 dengan status awal pending."""
    payload = build_register_payload(
        email="sinta@mail.com",
        phone="081234567890",
        program_studi_id=prodi_ti.id,
        jalur_masuk="SNBP",
    )
    res = client.post("/api/pmb/register", json=payload)

    assert res.status_code == 201
    body = res.json()
    assert body["id"] > 0
    assert body["email"] == "sinta@mail.com"
    assert body["status"] == "pending"
    assert body["program_studi_id"] == prodi_ti.id


def test_register_duplicate_email(client: TestClient, prodi_ti: ProgramStudi) -> None:
    """Email duplikat (termasuk berbeda huruf besar/kecil) ditolak dengan HTTP 409 Conflict."""
    first = daftar(client, "duplikat@mail.com", program_studi_id=prodi_ti.id)
    assert first.status_code == 201

    second = daftar(client, "DUPLIKAT@mail.com", program_studi_id=prodi_ti.id)
    assert second.status_code == 409
    assert "sudah terdaftar" in second.json()["detail"].lower()


def test_approve_generate_nim(client: TestClient, prodi_ti: ProgramStudi) -> None:
    """Approve dua pendaftar menghasilkan NIM sesuai format 11 digit dan berurutan (+1)."""
    a = daftar(client, "sinta@mail.com", program_studi_id=prodi_ti.id).json()
    b = daftar(client, "budi@mail.com", program_studi_id=prodi_ti.id).json()

    res_a = client.put(f"/api/pmb/approve/{a['id']}")
    res_b = client.put(f"/api/pmb/approve/{b['id']}")

    assert res_a.status_code == 200
    assert res_b.status_code == 200

    nim_a = res_a.json()["nim"]
    nim_b = res_b.json()["nim"]

    assert re.fullmatch(r"^\d{4}001\d{4}$", nim_a)
    assert re.fullmatch(r"^\d{4}001\d{4}$", nim_b)
    assert int(nim_b[-4:]) == int(nim_a[-4:]) + 1
    assert res_a.json()["status"] == "approved"
    assert res_a.json()["approved_at"] is not None


def test_approve_idempotent(client: TestClient, prodi_ti: ProgramStudi) -> None:
    """Approve 2x mengembalikan NIM identik DAN tidak diam-diam menaikkan counter."""
    a = daftar(client, "sinta@mail.com", program_studi_id=prodi_ti.id).json()
    b = daftar(client, "budi@mail.com", program_studi_id=prodi_ti.id).json()

    r1 = client.put(f"/api/pmb/approve/{a['id']}")
    r2 = client.put(f"/api/pmb/approve/{a['id']}")

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["nim"] == r2.json()["nim"]

    # Tes tajam dari video: pendaftar B setelah A di-approve 2x harus mendapat nomor 0002, bukan 0003
    rb = client.put(f"/api/pmb/approve/{b['id']}")
    assert rb.status_code == 200
    assert rb.json()["nim"].endswith("0002")


def test_invalid_phone_format(client: TestClient, prodi_ti: ProgramStudi) -> None:
    """Format telepon Indonesia yang invalid ditolak dengan HTTP 400 Bad Request."""
    payload = build_register_payload(
        email="invalidphone@mail.com",
        phone="12345",
        program_studi_id=prodi_ti.id,
    )
    res = client.post("/api/pmb/register", json=payload)

    assert res.status_code == 400


# ---------------------------------------------------------------------------
# Test Validasi Input & Edge Case Registrasi
# ---------------------------------------------------------------------------


def test_invalid_email_format(client: TestClient, prodi_ti: ProgramStudi) -> None:
    payload = build_register_payload(
        email="bukan-email-valid",
        program_studi_id=prodi_ti.id,
    )
    res = client.post("/api/pmb/register", json=payload)
    assert res.status_code == 400


def test_register_unknown_prodi_returns_400(client: TestClient, master_data: dict) -> None:
    payload = build_register_payload(email="noprodi@mail.com", program_studi_id=9999)
    res = client.post("/api/pmb/register", json=payload)
    assert res.status_code == 400
    assert "program studi" in res.json()["detail"].lower()


def test_register_future_birth_date_returns_400(client: TestClient, prodi_ti: ProgramStudi) -> None:
    besok = (date.today() + timedelta(days=1)).isoformat()
    payload = build_register_payload(
        email="masadepan@mail.com",
        tanggal_lahir=besok,
        program_studi_id=prodi_ti.id,
    )
    res = client.post("/api/pmb/register", json=payload)
    assert res.status_code == 400


def test_register_missing_master_jalur_returns_400(client: TestClient, db: Session) -> None:
    """Jika tabel jalur_masuk belum di-seed, registrasi ditolak dengan 400."""
    prodi = ProgramStudi(kode="001", nama="Teknik Informatika", fakultas="FIK")
    db.add(prodi)
    db.commit()
    db.refresh(prodi)

    res = daftar(client, "nojalur@mail.com", program_studi_id=prodi.id, jalur_masuk="SNBP")
    assert res.status_code == 400
    assert "jalur masuk" in res.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test Approve/Reject dengan Data Invalid & State Machine Guards
# ---------------------------------------------------------------------------


def test_approve_not_found(client: TestClient, master_data: dict) -> None:
    """Approve ID yang tidak ada mengembalikan HTTP 404 Not Found."""
    res = client.put("/api/pmb/approve/99999")
    assert res.status_code == 404
    assert "tidak ditemukan" in res.json()["detail"].lower()


def test_approve_rejected_returns_409(client: TestClient, prodi_ti: ProgramStudi) -> None:
    """Pendaftar yang sudah berstatus rejected tidak boleh di-approve (409 Conflict)."""
    calon = daftar(client, "ditolak@mail.com", program_studi_id=prodi_ti.id).json()

    reject_res = client.put(f"/api/pmb/reject/{calon['id']}")
    assert reject_res.status_code == 200
    assert reject_res.json()["status"] == "rejected"

    approve_res = client.put(f"/api/pmb/approve/{calon['id']}")
    assert approve_res.status_code == 409
    assert "bukan pending" in approve_res.json()["detail"].lower()


def test_approve_invalid_prodi_code_returns_400(
    client: TestClient,
    db: Session,
    master_data: dict,
) -> None:
    """Kode prodi bukan 3 digit angka tidak bisa dibuatkan NIM -> HTTP 400 Bad Request."""
    bad_prodi = ProgramStudi(kode="99", nama="Prodi Rusak", fakultas="Uji")
    db.add(bad_prodi)
    db.commit()
    db.refresh(bad_prodi)

    calon = daftar(client, "badprodi@mail.com", program_studi_id=bad_prodi.id).json()
    res = client.put(f"/api/pmb/approve/{calon['id']}")

    assert res.status_code == 400
    assert "3 digit" in res.json()["detail"].lower()


def test_approve_resets_counter_per_prodi(client: TestClient, master_data: dict) -> None:
    """NIM untuk prodi Sistem Informasi (002) tetap dimulai dari 0001 meski TI sudah punya pendaftar."""
    ti = master_data["prodi_ti"]
    si = master_data["prodi_si"]

    c_ti = daftar(client, "mhs_ti@mail.com", program_studi_id=ti.id).json()
    c_si = daftar(client, "mhs_si@mail.com", program_studi_id=si.id).json()

    nim_ti = client.put(f"/api/pmb/approve/{c_ti['id']}").json()["nim"]
    nim_si = client.put(f"/api/pmb/approve/{c_si['id']}").json()["nim"]

    assert nim_ti[4:7] == "001" and nim_ti.endswith("0001")
    assert nim_si[4:7] == "002" and nim_si.endswith("0001")


def test_reject_idempotent_and_guards(client: TestClient, prodi_ti: ProgramStudi) -> None:
    """Reject bersifat idempotent untuk rejected, namun 409 untuk approved dan 404 untuk ID hilang."""
    assert client.put("/api/pmb/reject/77777").status_code == 404

    c1 = daftar(client, "r1@mail.com", program_studi_id=prodi_ti.id).json()
    assert client.put(f"/api/pmb/reject/{c1['id']}").status_code == 200
    assert client.put(f"/api/pmb/reject/{c1['id']}").status_code == 200

    c2 = daftar(client, "r2@mail.com", program_studi_id=prodi_ti.id).json()
    assert client.put(f"/api/pmb/approve/{c2['id']}").status_code == 200
    res_conflict = client.put(f"/api/pmb/reject/{c2['id']}")
    assert res_conflict.status_code == 409


def test_approve_retry_recovers_from_transient_integrity_error(
    client: TestClient,
    db: Session,
    prodi_ti: ProgramStudi,
) -> None:
    """Jika terjadi IntegrityError sementara (simulasi tabrakan paralel), approve rollback & retry sukses."""
    calon = daftar(client, "retry@mail.com", program_studi_id=prodi_ti.id).json()

    real_commit = db.commit
    state = {"failed_once": False}

    def flaky_commit() -> None:
        if not state["failed_once"]:
            state["failed_once"] = True
            raise IntegrityError("INSERT", {}, Exception("simulated unique collision"))
        real_commit()

    with patch.object(db, "commit", side_effect=flaky_commit):
        res = client.put(f"/api/pmb/approve/{calon['id']}")

    assert res.status_code == 200
    assert state["failed_once"] is True
    assert res.json()["nim"].endswith("0001")


def test_approve_exhausted_retries_returns_409(
    client: TestClient,
    db: Session,
    prodi_ti: ProgramStudi,
) -> None:
    """Jika IntegrityError terjadi terus-menerus hingga batas retry habis, kembalikan 409."""
    calon = daftar(client, "failretry@mail.com", program_studi_id=prodi_ti.id).json()

    with patch.object(
        db,
        "commit",
        side_effect=IntegrityError("INSERT", {}, Exception("persistent collision")),
    ):
        res = client.put(f"/api/pmb/approve/{calon['id']}")

    assert res.status_code == 409


# ---------------------------------------------------------------------------
# Test GET /status/{id}, GET /stats, Swagger, & DB Constraints
# ---------------------------------------------------------------------------


def test_get_status_filters_private_data(client: TestClient, prodi_ti: ProgramStudi) -> None:
    """GET /status/{id} hanya menampilkan data status & NIM, tanpa data pribadi sensitif."""
    assert client.get("/api/pmb/status/99999").status_code == 404

    calon = daftar(client, "privat@mail.com", program_studi_id=prodi_ti.id).json()
    res_pending = client.get(f"/api/pmb/status/{calon['id']}")
    assert res_pending.status_code == 200
    data_pending = res_pending.json()
    assert data_pending["status"] == "pending"
    assert data_pending["nim"] is None
    # Pastikan data pribadi tidak ikut keluar lewat response_model StatusOut
    for forbidden_key in ("email", "phone", "alamat", "tanggal_lahir"):
        assert forbidden_key not in data_pending

    client.put(f"/api/pmb/approve/{calon['id']}")
    res_approved = client.get(f"/api/pmb/status/{calon['id']}")
    assert res_approved.status_code == 200
    assert res_approved.json()["status"] == "approved"
    assert res_approved.json()["nim"] is not None


def test_get_stats_group_by_and_zero_entries(client: TestClient, master_data: dict) -> None:
    """GET /stats menghitung agregasi DB termasuk prodi & jalur yang masih 0 pendaftar."""
    ti = master_data["prodi_ti"]
    si = master_data["prodi_si"]

    c1 = daftar(client, "a@mail.com", program_studi_id=ti.id, jalur_masuk="SNBP").json()
    c2 = daftar(client, "b@mail.com", program_studi_id=ti.id, jalur_masuk="SNBT").json()
    daftar(client, "c@mail.com", program_studi_id=si.id, jalur_masuk="SNBP")

    client.put(f"/api/pmb/approve/{c1['id']}")
    client.put(f"/api/pmb/reject/{c2['id']}")

    res = client.get("/api/pmb/stats")
    assert res.status_code == 200
    stats = res.json()

    assert stats["total"] == 3
    assert stats["per_status"] == {"pending": 1, "approved": 1, "rejected": 1}
    assert stats["per_prodi"]["Teknik Informatika"] == 2
    assert stats["per_prodi"]["Sistem Informasi"] == 1
    assert stats["per_prodi"]["Teknik Elektro"] == 0
    assert stats["per_jalur_masuk"] == {"SNBP": 2, "SNBT": 1, "Mandiri": 0}


def test_swagger_docs_and_health(client: TestClient) -> None:
    """Dokumentasi OpenAPI/Swagger (/docs, /redoc, /openapi.json) dan /health tersedia."""
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200

    openapi = client.get("/openapi.json")
    assert openapi.status_code == 200
    paths = openapi.json()["paths"]
    for expected in (
        "/api/pmb/register",
        "/api/pmb/status/{calon_id}",
        "/api/pmb/approve/{calon_id}",
        "/api/pmb/reject/{calon_id}",
        "/api/pmb/stats",
    ):
        assert expected in paths


def test_database_check_constraint_rejects_bad_phone(db: Session, prodi_ti: ProgramStudi) -> None:
    """Constraint level database menolak nomor telepon invalid meski melewati Pydantic."""
    bad_row = CalonMahasiswa(
        nama_lengkap="Bypass Pydantic",
        email="bypass@mail.com",
        phone="12345",
        tanggal_lahir=date(2005, 1, 1),
        alamat="Jl. Uji Constraint",
        program_studi_id=prodi_ti.id,
        jalur_masuk="SNBP",
        status=StatusPMB.PENDING,
    )
    db.add(bad_row)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
