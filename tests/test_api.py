"""End-to-end API tests dengan FastAPI TestClient untuk router nilai, GPA, audit trail, dan form web."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_form_web_dapat_diakses(client: TestClient) -> None:
    res = client.get("/")
    assert res.status_code == 200
    assert "SEVIMA-Mini" in res.text


def test_put_nilai_tanpa_header_login_401(client: TestClient) -> None:
    res = client.put("/api/kelas/5/nilai/2025004", json={"huruf": "A"})
    assert res.status_code == 401


def test_put_nilai_huruf_invalid_ditolak_pydantic_422(client: TestClient) -> None:
    for huruf_invalid in ["A+", "a", "F", ""]:
        res = client.put(
            "/api/kelas/5/nilai/2025004",
            headers={"X-Dosen-Id": "1"},
            json={"huruf": huruf_invalid},
        )
        assert res.status_code == 422


def test_put_nilai_non_pengampu_403_dan_presensi_rendah_400(client: TestClient) -> None:
    # Dosen 2 bukan pengampu kelas 5 (Basis Data A) -> 403
    res_403 = client.put(
        "/api/kelas/5/nilai/2025004",
        headers={"X-Dosen-Id": "2"},
        json={"huruf": "A"},
    )
    assert res_403.status_code == 403

    # Budi (2025002) presensi 70% < 75% -> 400
    res_400 = client.put(
        "/api/kelas/5/nilai/2025002",
        headers={"X-Dosen-Id": "1"},
        json={"huruf": "B"},
    )
    assert res_400.status_code == 400
    assert "75%" in res_400.json()["detail"]


def test_input_dan_edit_nilai_otomatis_mengupdate_ipk_dan_audit_trail(client: TestClient) -> None:
    # 1. Cek IPK awal Dimas (mahasiswa baru tanpa nilai) -> "0.00" (string!)
    res_ipk_awal = client.get("/api/mahasiswa/2025004/ipk")
    assert res_ipk_awal.status_code == 200
    assert res_ipk_awal.json() == {"nim": "2025004", "ipk": "0.00"}
    assert isinstance(res_ipk_awal.json()["ipk"], str)

    # 2. Dosen pengampu (ID 1) input nilai perdana B untuk Dimas (presensi tepat 75%)
    res_put = client.put(
        "/api/kelas/5/nilai/2025004",
        headers={"X-Dosen-Id": "1"},
        json={"huruf": "B"},
    )
    assert res_put.status_code == 200
    assert res_put.json() == {"nim": "2025004", "kode_mk": "IF202", "huruf": "B"}

    # 3. IPK langsung ter-update otomatis (compute-on-read) menjadi "3.00"
    res_ipk_baru = client.get("/api/mahasiswa/2025004/ipk")
    assert res_ipk_baru.json() == {"nim": "2025004", "ipk": "3.00"}

    # 4. Edit nilai tanpa alasan ditolak 400
    res_edit_gagal = client.put(
        "/api/kelas/5/nilai/2025004",
        headers={"X-Dosen-Id": "1"},
        json={"huruf": "A"},
    )
    assert res_edit_gagal.status_code == 400

    # 5. Edit nilai dengan alasan berhasil -> IPK jadi "4.00" & riwayat lengkap
    res_edit_ok = client.put(
        "/api/kelas/5/nilai/2025004",
        headers={"X-Dosen-Id": "1"},
        json={"huruf": "A", "alasan": "Perbaikan input nilai proyek akhir"},
    )
    assert res_edit_ok.status_code == 200
    assert client.get("/api/mahasiswa/2025004/ipk").json()["ipk"] == "4.00"

    # 6. Cek endpoint riwayat nilai dari view v_riwayat_nilai
    res_hist = client.get("/api/mahasiswa/2025004/riwayat-nilai")
    assert res_hist.status_code == 200
    rows = res_hist.json()
    assert len(rows) == 2
    assert rows[0]["old_value"] == "B"
    assert rows[0]["new_value"] == "A"
    assert rows[0]["reason"] == "Perbaikan input nilai proyek akhir"
    assert rows[1]["old_value"] is None
    assert rows[1]["new_value"] == "B"


def test_ips_dan_peserta_kelas_endpoints(client: TestClient) -> None:
    res_ips = client.get("/api/mahasiswa/2025001/ips/20241")
    assert res_ips.status_code == 200
    assert res_ips.json() == {"nim": "2025001", "semester": "20241", "ips": "2.44"}

    res_peserta = client.get("/api/kelas/5/peserta")
    assert res_peserta.status_code == 200
    peserta = {p["nim"]: p for p in res_peserta.json()}
    assert peserta["2025002"]["terkunci"] is True
    assert peserta["2025001"]["terkunci"] is False
    assert peserta["2025001"]["ipk_saat_ini"] == "3.08"
