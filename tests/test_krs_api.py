"""API tests menggunakan FastAPI TestClient untuk verifikasi status code & payload."""


def test_api_tambah_hapus_dan_validasi_mk(client):
    # Tambah BD1 -> 201
    res = client.post("/api/krs/2026001/courses", json={"kode_mk": "BD1"})
    assert res.status_code == 201
    assert res.json()["total_sks"] == 3

    # Tambah KAL2 tanpa prasyarat -> 400 dengan pesan jelas
    res = client.post("/api/krs/2026001/courses", json={"kode_mk": "KAL2"})
    assert res.status_code == 400
    assert res.json()["detail"] == "Prasyarat tidak terpenuhi: Kalkulus I"

    # Tambah PBO1 bentrok dengan BD1 -> 400
    res = client.post("/api/krs/2026001/courses", json={"kode_mk": "PBO1"})
    assert res.status_code == 400
    assert "Jadwal bentrok" in res.json()["detail"]

    # Validasi KRS -> valid
    res = client.get("/api/krs/2026001/validate")
    assert res.status_code == 200
    assert res.json() == {"valid": True, "errors": []}

    # Hapus BD1 -> 200
    res = client.delete("/api/krs/2026001/courses/BD1")
    assert res.status_code == 200
    assert res.json()["total_sks"] == 0


def test_api_state_machine_kode_400_403_409_422(client):
    # Submit KRS kosong -> 400
    res = client.post("/api/krs/2026001/submit")
    assert res.status_code == 400
    assert "KRS kosong" in res.json()["detail"]

    # Approve saat masih DRAFT oleh dosen PA sah -> 409 Conflict (tidak boleh lompat)
    res = client.post(
        "/api/krs/2026001/approve", json={"dosen_pa_id": 101}
    )
    assert res.status_code == 409
    assert "DRAFT ke APPROVED" in res.json()["detail"]

    # Isi MK dan submit -> 200
    client.post("/api/krs/2026001/courses", json={"kode_mk": "BD1"})
    res = client.post("/api/krs/2026001/submit")
    assert res.status_code == 200
    data_submitted = res.json()
    assert data_submitted["status"] == "SUBMITTED"
    versi_aktif = data_submitted["version"]

    # Double submit -> 409 Conflict
    res = client.post("/api/krs/2026001/submit")
    assert res.status_code == 409

    # Tambah MK saat SUBMITTED -> 409 Conflict (terkunci)
    res = client.post("/api/krs/2026001/courses", json={"kode_mk": "ALGO"})
    assert res.status_code == 409

    # Dosen lain mencoba approve -> 403 Forbidden
    res = client.post(
        "/api/krs/2026001/approve",
        json={"dosen_pa_id": 999, "version": versi_aktif},
    )
    assert res.status_code == 403
    assert "bukan dosen PA" in res.json()["detail"]

    # Revise tanpa catatan -> 422 Unprocessable Entity
    res = client.post(
        "/api/krs/2026001/revise",
        json={"dosen_pa_id": 101, "catatan": "   "},
    )
    assert res.status_code == 422

    # Revise dengan catatan valid -> 200
    res = client.post(
        "/api/krs/2026001/revise",
        json={"dosen_pa_id": 101, "catatan": "Ambil MK wajib dulu"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "REVISION"

    # Submit ulang -> 200
    res = client.post("/api/krs/2026001/submit")
    assert res.status_code == 200
    versi_baru = res.json()["version"]

    # Approve dengan versi basi -> 409 Conflict
    res = client.post(
        "/api/krs/2026001/approve",
        json={"dosen_pa_id": 101, "version": versi_aktif},
    )
    assert res.status_code == 409
    assert "muat ulang" in res.json()["detail"]

    # Approve dengan versi terbaru -> 200
    res = client.post(
        "/api/krs/2026001/approve",
        json={"dosen_pa_id": 101, "version": versi_baru},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "APPROVED"


def test_api_recommend_krs_challenge(client):
    res = client.post(
        "/api/krs/2026002/recommend",
        json={
            "desired_courses": ["BD1", "PBO1", "KAL2", "ML1", "ALGO"],
            "max_sks": 24,
            "target_sks": 20,
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["validated"] is True
    assert body["total_sks"] <= 24
    kode_terpilih = {mk["kode_mk"] for mk in body["selected_courses"]}
    # BD1(WAJIB) & PBO1-B(kelas paralel non-bentrok) dipilih, ML1(PILIHAN bentrok BD1) tidak
    assert "BD1" in kode_terpilih
    assert "PBO1-B" in kode_terpilih
    assert "ML1" not in kode_terpilih
