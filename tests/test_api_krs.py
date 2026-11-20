"""Integration tests untuk endpoint FastAPI Modul KRS."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_endpoint(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_api_add_get_validate_and_remove_course(client: TestClient) -> None:
    # 1. Ambil KRS awal Budi (202401001) -> otomatis dibuat DRAFT kosong
    resp = client.get("/api/krs/202401001?semester=20251")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "DRAFT"
    assert data["total_sks"] == 0

    # 2. Tambah Struktur Data (IF201, 4 SKS) -> 201 Created
    resp = client.post("/api/krs/202401001/courses?semester=20251", json={"kode_mk": "IF201"})
    assert resp.status_code == 201
    assert resp.json()["kode_mk"] == "IF201"
    assert resp.json()["matakuliah"]["nama"] == "Struktur Data"

    # 3. Coba tambah Kalkulus II (MA201) -> 400 Bad Request (Budi dapat D di Kalkulus I)
    resp = client.post("/api/krs/202401001/courses?semester=20251", json={"kode_mk": "MA201"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Prasyarat tidak terpenuhi: Kalkulus I"

    # 4. Validasi menyeluruh -> valid=True
    resp = client.get("/api/krs/202401001/validate?semester=20251")
    assert resp.status_code == 200
    assert resp.json()["valid"] is True
    assert resp.json()["issues"] == []

    # 5. Hapus IF201 -> 200 OK
    resp = client.delete("/api/krs/202401001/courses/IF201?semester=20251")
    assert resp.status_code == 200
    assert "berhasil dihapus" in resp.json()["message"]

    # 6. Hapus ulang IF201 -> 404 Not Found
    resp = client.delete("/api/krs/202401001/courses/IF201?semester=20251")
    assert resp.status_code == 404


def test_api_conflict_and_submitted_status_responses(client: TestClient) -> None:
    # Ani (202401002) tambah Basis Data (Senin 08:00-10:30), lalu Statistika (Senin 09:00-11:00)
    resp1 = client.post("/api/krs/202401002/courses?semester=20251", json={"kode_mk": "IF202"})
    assert resp1.status_code == 201

    resp2 = client.post("/api/krs/202401002/courses?semester=20251", json={"kode_mk": "IF203"})
    assert resp2.status_code == 400
    assert resp2.json()["detail"] == "Jadwal bentrok: Statistika dengan Basis Data"

    # Citra (202401003) berstatus SUBMITTED -> 409 Conflict
    resp3 = client.post("/api/krs/202401003/courses?semester=20251", json={"kode_mk": "IF204"})
    assert resp3.status_code == 409
    assert "SUBMITTED" in resp3.json()["detail"]

    # NIM tidak terdaftar -> 404 Not Found
    resp4 = client.get("/api/krs/999999999?semester=20251")
    assert resp4.status_code == 404
