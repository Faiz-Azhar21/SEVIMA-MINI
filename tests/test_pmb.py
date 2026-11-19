import re
import pytest

def test_register_success(client):
    payload = {
        "nama_lengkap": "Ahmad Fauzi",
        "email": "ahmad.fauzi@example.com",
        "phone": "081234567890",
        "tanggal_lahir": "2005-04-12",
        "alamat": "Jl. Merdeka No. 45, Jakarta",
        "program_studi_id": 1,
        "jalur_masuk": "SNBP"
    }
    response = client.post("/api/pmb/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["nama_lengkap"] == payload["nama_lengkap"]
    assert data["email"] == payload["email"]
    assert data["status"] == "pending"
    assert data["nim"] is None

def test_register_duplicate_email(client):
    payload = {
        "nama_lengkap": "Siti Nurhaliza",
        "email": "siti.nur@example.com",
        "phone": "081298765432",
        "tanggal_lahir": "2005-08-20",
        "alamat": "Jl. Sudirman No. 12, Bandung",
        "program_studi_id": 1,
        "jalur_masuk": "SNBT"
    }
    # Registrasi pertama: Berhasil (201)
    res1 = client.post("/api/pmb/register", json=payload)
    assert res1.status_code == 201

    # Registrasi kedua dengan email yang sama: Harus 409 Conflict
    res2 = client.post("/api/pmb/register", json=payload)
    assert res2.status_code == 409
    assert "sudah terdaftar" in res2.json()["detail"]

def test_invalid_phone_format(client):
    invalid_phones = ["123456", "0217894561", "071199999", "abcdefghijk", "+123456789012"]
    for phone in invalid_phones:
        payload = {
            "nama_lengkap": "User Test",
            "email": f"user_{phone}@example.com",
            "phone": phone,
            "tanggal_lahir": "2005-01-01",
            "alamat": "Jl. Percobaan No. 1",
            "program_studi_id": 1,
            "jalur_masuk": "SNBP"
        }
        res = client.post("/api/pmb/register", json=payload)
        assert res.status_code == 400

def test_invalid_email_format(client):
    payload = {
        "nama_lengkap": "Test Email Invalid",
        "email": "bukan-email-valid",
        "phone": "081234567890",
        "tanggal_lahir": "2005-01-01",
        "alamat": "Jl. Percobaan No. 1",
        "program_studi_id": 1,
        "jalur_masuk": "SNBP"
    }
    res = client.post("/api/pmb/register", json=payload)
    assert res.status_code == 400

def test_invalid_program_studi_id(client):
    payload = {
        "nama_lengkap": "Test Prodi Invalid",
        "email": "testprodi@example.com",
        "phone": "081234567890",
        "tanggal_lahir": "2005-01-01",
        "alamat": "Jl. Percobaan No. 1",
        "program_studi_id": 9999,
        "jalur_masuk": "SNBP"
    }
    res = client.post("/api/pmb/register", json=payload)
    assert res.status_code == 400
    assert "Program Studi dengan ID 9999 tidak ditemukan" in res.json()["detail"]

def test_invalid_jalur_masuk(client):
    payload = {
        "nama_lengkap": "Test Jalur Invalid",
        "email": "testjalur@example.com",
        "phone": "081234567890",
        "tanggal_lahir": "2005-01-01",
        "alamat": "Jl. Percobaan No. 1",
        "program_studi_id": 1,
        "jalur_masuk": "JALUR_GAIB"
    }
    res = client.post("/api/pmb/register", json=payload)
    assert res.status_code == 400

def test_get_status_success(client):
    payload = {
        "nama_lengkap": "Rian Pratama",
        "email": "rian.pratama@example.com",
        "phone": "081234567891",
        "tanggal_lahir": "2005-05-15",
        "alamat": "Jl. Diponegoro No. 8, Surabaya",
        "program_studi_id": 1,
        "jalur_masuk": "Mandiri"
    }
    reg_res = client.post("/api/pmb/register", json=payload)
    assert reg_res.status_code == 201
    applicant_id = reg_res.json()["id"]

    status_res = client.get(f"/api/pmb/status/{applicant_id}")
    assert status_res.status_code == 200
    data = status_res.json()
    assert data["id"] == applicant_id
    assert data["nama_lengkap"] == "Rian Pratama"
    assert data["status"] == "pending"
    assert data["nim"] is None

def test_get_status_not_found(client):
    res = client.get("/api/pmb/status/99999")
    assert res.status_code == 404
    assert "tidak ditemukan" in res.json()["detail"]

def test_approve_generate_nim(client):
    payload1 = {
        "nama_lengkap": "Dewi Sartika",
        "email": "dewi.sartika@example.com",
        "phone": "081234567892",
        "tanggal_lahir": "2005-06-10",
        "alamat": "Jl. Gatot Subroto No. 3, Medan",
        "program_studi_id": 1,
        "jalur_masuk": "SNBP"
    }
    reg_res1 = client.post("/api/pmb/register", json=payload1)
    id1 = reg_res1.json()["id"]

    payload2 = {
        "nama_lengkap": "Bambang Pamungkas",
        "email": "bambang@example.com",
        "phone": "081234567893",
        "tanggal_lahir": "2005-07-11",
        "alamat": "Jl. Asia Afrika No. 4, Bandung",
        "program_studi_id": 1,
        "jalur_masuk": "SNBT"
    }
    reg_res2 = client.post("/api/pmb/register", json=payload2)
    id2 = reg_res2.json()["id"]

    approve_res1 = client.put(f"/api/pmb/approve/{id1}")
    assert approve_res1.status_code == 200
    data1 = approve_res1.json()
    assert data1["status"] == "approved"
    nim1 = data1["nim"]
    assert re.match(r"^\d{4}001-0001$", nim1)

    approve_res2 = client.put(f"/api/pmb/approve/{id2}")
    assert approve_res2.status_code == 200
    data2 = approve_res2.json()
    assert data2["status"] == "approved"
    nim2 = data2["nim"]
    assert re.match(r"^\d{4}001-0002$", nim2)
    assert nim1 != nim2

def test_approve_idempotent(client):
    payload = {
        "nama_lengkap": "Indra Sjafri",
        "email": "indra.sjafri@example.com",
        "phone": "081234567894",
        "tanggal_lahir": "2005-08-12",
        "alamat": "Jl. Pemuda No. 22, Padang",
        "program_studi_id": 2,
        "jalur_masuk": "SNBP"
    }
    reg_res = client.post("/api/pmb/register", json=payload)
    applicant_id = reg_res.json()["id"]

    res1 = client.put(f"/api/pmb/approve/{applicant_id}")
    assert res1.status_code == 200
    nim_first = res1.json()["nim"]
    assert nim_first is not None
    assert "-0001" in nim_first

    res2 = client.put(f"/api/pmb/approve/{applicant_id}")
    assert res2.status_code == 200
    nim_second = res2.json()["nim"]
    assert nim_second == nim_first

    status_res = client.get(f"/api/pmb/status/{applicant_id}")
    assert status_res.status_code == 200
    assert status_res.json()["nim"] == nim_first
    assert status_res.json()["status"] == "approved"

def test_approve_invalid_id(client):
    res = client.put("/api/pmb/approve/999999")
    assert res.status_code == 404
    assert "tidak ditemukan" in res.json()["detail"]

def test_stats_endpoint(client):
    client.post("/api/pmb/register", json={
        "nama_lengkap": "User Stats 1",
        "email": "stats1@example.com",
        "phone": "081234567895",
        "tanggal_lahir": "2005-01-01",
        "alamat": "Alamat 1",
        "program_studi_id": 1,
        "jalur_masuk": "SNBP"
    })
    reg2 = client.post("/api/pmb/register", json={
        "nama_lengkap": "User Stats 2",
        "email": "stats2@example.com",
        "phone": "081234567896",
        "tanggal_lahir": "2005-01-02",
        "alamat": "Alamat 2",
        "program_studi_id": 2,
        "jalur_masuk": "SNBT"
    })
    id2 = reg2.json()["id"]

    client.put(f"/api/pmb/approve/{id2}")

    stats_res = client.get("/api/pmb/stats")
    assert stats_res.status_code == 200
    stats = stats_res.json()
    assert stats["total_pendaftar"] >= 2
    assert stats["by_status"]["pending"] >= 1
    assert stats["by_status"]["approved"] >= 1
    assert "Teknik Informatika" in stats["by_program_studi"]
    assert "SNBP" in stats["by_jalur_masuk"]

def test_endpoint_aliases(client):
    payload = {
        "nama_lengkap": "Alias Route Test",
        "email": "alias.test@example.com",
        "phone": "081234567897",
        "tanggal_lahir": "2005-09-09",
        "alamat": "Jl. Tol Jagorawi",
        "program_studi_id": 1,
        "jalur_masuk": "SNBP"
    }
    res = client.post("/register", json=payload)
    assert res.status_code == 201
    calon_id = res.json()["id"]

    res_status = client.get(f"/status/{calon_id}")
    assert res_status.status_code == 200

    res_approve = client.put(f"/approve/{calon_id}")
    assert res_approve.status_code == 200

    res_stats = client.get("/stats")
    assert res_stats.status_code == 200

def test_master_data_and_ui_endpoints(client):
    # Test GET /api/pmb/prodi
    res_prodi = client.get("/api/pmb/prodi")
    assert res_prodi.status_code == 200
    prodi_data = res_prodi.json()
    assert len(prodi_data) >= 3
    assert any(p["kode"] == "001" for p in prodi_data)

    # Test GET /api/pmb/jalur
    res_jalur = client.get("/api/pmb/jalur")
    assert res_jalur.status_code == 200
    jalur_data = res_jalur.json()
    assert len(jalur_data) >= 3
    assert any(j["kode"] == "SNBP" for j in jalur_data)

    # Test GET /api/pmb/list
    res_list = client.get("/api/pmb/list")
    assert res_list.status_code == 200

    # Test GET / (HTML Home)
    res_home = client.get("/")
    assert res_home.status_code == 200
