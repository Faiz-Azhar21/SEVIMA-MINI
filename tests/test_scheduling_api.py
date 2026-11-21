"""Integration & API tests untuk SchedulingService, Router /api/jadwal, Seed, dan Alembic."""

from __future__ import annotations

from datetime import time
from pathlib import Path

from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from app.models.jadwal import Jadwal
from app.models.krs import KRS, KRSDetail
from scripts.seed import seed_database


def test_post_jadwal_sukses_201(client: TestClient, sample_entities: dict) -> None:
    payload = {
        "kelas_id": sample_entities["kelas"]["bd_a"].id,
        "hari": 1,
        "jam_mulai": "08:00:00",
        "jam_selesai": "09:40:00",
        "ruangan_kode": "A101",
        "dosen_id": sample_entities["dosen"][0].id,
    }
    r = client.post("/api/jadwal", json=payload)
    assert r.status_code == 201
    body = r.json()
    assert body["id"] >= 1
    assert body["ruangan_kode"] == "A101"
    assert body["jam_mulai"] == "08:00:00"
    assert body["jam_selesai"] == "09:40:00"


def test_post_bentrok_ruangan_409(
    client: TestClient, sample_entities: dict, jadwal_a101: Jadwal
) -> None:
    # jadwal_a101: Senin 08:00-09:40 di A101 oleh dosen 1
    r = client.post(
        "/api/jadwal",
        json={
            "kelas_id": sample_entities["kelas"]["stat_b"].id,
            "hari": 1,
            "jam_mulai": "09:00",
            "jam_selesai": "10:40",
            "ruangan_kode": "A101",
            "dosen_id": sample_entities["dosen"][1].id,
        },
    )
    assert r.status_code == 409
    data = r.json()
    assert len(data["conflicts"]) == 1
    assert data["conflicts"][0]["type"] == "room_conflict"
    assert data["conflicts"][0]["affected"] == [jadwal_a101.id]


def test_post_bentrok_dosen_409(
    client: TestClient, sample_entities: dict, jadwal_a101: Jadwal
) -> None:
    r = client.post(
        "/api/jadwal",
        json={
            "kelas_id": sample_entities["kelas"]["stat_b"].id,
            "hari": 1,
            "jam_mulai": "08:30",
            "jam_selesai": "10:10",
            "ruangan_kode": "B201",  # ruang berbeda, dosen sama
            "dosen_id": sample_entities["dosen"][0].id,
        },
    )
    assert r.status_code == 409
    data = r.json()
    assert len(data["conflicts"]) == 1
    assert data["conflicts"][0]["type"] == "lecturer_conflict"
    assert data["conflicts"][0]["affected"] == [jadwal_a101.id]


def test_post_bentrok_ganda_melaporkan_kedua_tipe_409(
    client: TestClient, sample_entities: dict, jadwal_a101: Jadwal
) -> None:
    r = client.post(
        "/api/jadwal",
        json={
            "kelas_id": sample_entities["kelas"]["stat_b"].id,
            "hari": 1,
            "jam_mulai": "08:30",
            "jam_selesai": "09:10",
            "ruangan_kode": "A101",
            "dosen_id": sample_entities["dosen"][0].id,
        },
    )
    assert r.status_code == 409
    types = {c["type"] for c in r.json()["conflicts"]}
    assert types == {"room_conflict", "lecturer_conflict"}


def test_post_kuliah_bersambung_0940_diizinkan_201(
    client: TestClient, sample_entities: dict, jadwal_a101: Jadwal
) -> None:
    """Interval setengah terbuka: tepat pukul 09:40 tidak bentrok."""
    r = client.post(
        "/api/jadwal",
        json={
            "kelas_id": sample_entities["kelas"]["stat_b"].id,
            "hari": 1,
            "jam_mulai": "09:40",
            "jam_selesai": "11:20",
            "ruangan_kode": "A101",
            "dosen_id": sample_entities["dosen"][0].id,
        },
    )
    assert r.status_code == 201


def test_post_kapasitas_tepat_sama_boleh_201(
    client: TestClient, sample_entities: dict
) -> None:
    """stat_b berkuota 40, ruang A101 berkapasitas 40 -> 40 <= 40 harus BOLEH."""
    r = client.post(
        "/api/jadwal",
        json={
            "kelas_id": sample_entities["kelas"]["stat_b"].id,
            "hari": 2,
            "jam_mulai": "08:00",
            "jam_selesai": "09:40",
            "ruangan_kode": "A101",
            "dosen_id": sample_entities["dosen"][0].id,
        },
    )
    assert r.status_code == 201


def test_post_kapasitas_awal_semester_kuota_melebihi_ruang_409(
    client: TestClient, sample_entities: dict
) -> None:
    """Walau terdaftar = 0, kelas berkuota 50 tidak boleh masuk ruang berkapasitas 40."""
    r = client.post(
        "/api/jadwal",
        json={
            "kelas_id": sample_entities["kelas"]["besar"].id,
            "hari": 2,
            "jam_mulai": "08:00",
            "jam_selesai": "09:40",
            "ruangan_kode": "A101",
            "dosen_id": sample_entities["dosen"][0].id,
        },
    )
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert "A101" in detail
    assert "40" in detail
    assert "50" in detail


def test_post_kapasitas_terdaftar_melebihi_ruang_409(
    client: TestClient, db_session: Session, sample_entities: dict
) -> None:
    """Jika peserta terdaftar di KRSDetail > kapasitas ruang, harus ditolak 409."""
    kelas_bd = sample_entities["kelas"]["bd_a"]  # kuota=35
    kelas_bd.kuota = 20  # kuota kecil, tapi terdaftar = 26 > kapasitas LAB1 (25)
    for i in range(26):
        krs = KRS(nim=f"23020{i:03d}", semester="20251", status="APPROVED")
        db_session.add(krs)
        db_session.flush()
        db_session.add(
            KRSDetail(krs_id=krs.id, kode_mk=kelas_bd.kode_mk, kelas_id=kelas_bd.id)
        )
    db_session.commit()

    r = client.post(
        "/api/jadwal",
        json={
            "kelas_id": kelas_bd.id,
            "hari": 3,
            "jam_mulai": "08:00",
            "jam_selesai": "09:40",
            "ruangan_kode": "LAB1",  # kapasitas 25
            "dosen_id": sample_entities["dosen"][0].id,
        },
    )
    assert r.status_code == 409
    assert "26" in r.json()["detail"]
    assert "25" in r.json()["detail"]


def test_post_validasi_pydantic_422(client: TestClient, sample_entities: dict) -> None:
    """Jam selesai <= jam mulai atau hari di luar 1..6 ditolak Pydantic (422)."""
    r_jam = client.post(
        "/api/jadwal",
        json={
            "kelas_id": sample_entities["kelas"]["bd_a"].id,
            "hari": 1,
            "jam_mulai": "10:00",
            "jam_selesai": "09:00",
            "ruangan_kode": "A101",
            "dosen_id": sample_entities["dosen"][0].id,
        },
    )
    assert r_jam.status_code == 422

    r_hari = client.post(
        "/api/jadwal",
        json={
            "kelas_id": sample_entities["kelas"]["bd_a"].id,
            "hari": 7,
            "jam_mulai": "08:00",
            "jam_selesai": "09:40",
            "ruangan_kode": "A101",
            "dosen_id": sample_entities["dosen"][0].id,
        },
    )
    assert r_hari.status_code == 422


def test_post_entitas_tidak_ditemukan_404(
    client: TestClient, sample_entities: dict
) -> None:
    r_ruang = client.post(
        "/api/jadwal",
        json={
            "kelas_id": sample_entities["kelas"]["bd_a"].id,
            "hari": 1,
            "jam_mulai": "08:00",
            "jam_selesai": "09:40",
            "ruangan_kode": "Z999",  # ruangan tidak ada
            "dosen_id": sample_entities["dosen"][0].id,
        },
    )
    assert r_ruang.status_code == 404

    r_dosen = client.post(
        "/api/jadwal",
        json={
            "kelas_id": sample_entities["kelas"]["bd_a"].id,
            "hari": 1,
            "jam_mulai": "08:00",
            "jam_selesai": "09:40",
            "ruangan_kode": "A101",
            "dosen_id": 99999,  # dosen tidak ada
        },
    )
    assert r_dosen.status_code == 404

    r_kelas = client.post(
        "/api/jadwal",
        json={
            "kelas_id": 99999,  # kelas tidak ada
            "hari": 1,
            "jam_mulai": "08:00",
            "jam_selesai": "09:40",
            "ruangan_kode": "A101",
            "dosen_id": sample_entities["dosen"][0].id,
        },
    )
    assert r_kelas.status_code == 404


def test_get_daftar_jadwal_dan_put_bentrok_rollback(
    client: TestClient, sample_entities: dict, jadwal_a101: Jadwal
) -> None:
    """GET /api/jadwal mengembalikan jadwal; PUT bentrok ditolak 409 & data lama tetap utuh."""
    r_baru = client.post(
        "/api/jadwal",
        json={
            "kelas_id": sample_entities["kelas"]["stat_b"].id,
            "hari": 2,
            "jam_mulai": "10:00",
            "jam_selesai": "11:40",
            "ruangan_kode": "B201",
            "dosen_id": sample_entities["dosen"][1].id,
        },
    )
    assert r_baru.status_code == 201
    jadwal_kedua_id = r_baru.json()["id"]

    # Pindahkan jadwal kedua ke slot yang bentrok dengan jadwal_a101 -> harus 409
    r_bentrok = client.put(
        f"/api/jadwal/{jadwal_kedua_id}",
        json={
            "kelas_id": sample_entities["kelas"]["stat_b"].id,
            "hari": 1,
            "jam_mulai": "08:30",
            "jam_selesai": "10:00",
            "ruangan_kode": "A101",
            "dosen_id": sample_entities["dosen"][1].id,
        },
    )
    assert r_bentrok.status_code == 409

    # Pastikan GET /api/jadwal masih menampilkan 2 jadwal dengan jadwal kedua tetap di hari 2
    r_list = client.get("/api/jadwal")
    assert r_list.status_code == 200
    items = r_list.json()
    assert len(items) == 2
    kedua = next(i for i in items if i["id"] == jadwal_kedua_id)
    assert kedua["hari"] == 2
    assert kedua["ruangan_kode"] == "B201"


def test_put_geser_15_menit_tidak_bentrok_dengan_diri_sendiri(
    client: TestClient, sample_entities: dict, jadwal_a101: Jadwal
) -> None:
    """Saat update, jadwal sendiri dikecualikan agar geser 15 menit tetap sukses (200)."""
    r = client.put(
        f"/api/jadwal/{jadwal_a101.id}",
        json={
            "kelas_id": jadwal_a101.kelas_id,
            "hari": 1,
            "jam_mulai": "08:15",
            "jam_selesai": "09:55",
            "ruangan_kode": "A101",
            "dosen_id": jadwal_a101.dosen_id,
        },
    )
    assert r.status_code == 200
    assert r.json()["jam_mulai"] == "08:15:00"


def test_put_tidak_ditemukan_404(client: TestClient, sample_entities: dict) -> None:
    r = client.put(
        "/api/jadwal/99999",
        json={
            "kelas_id": sample_entities["kelas"]["bd_a"].id,
            "hari": 1,
            "jam_mulai": "08:00",
            "jam_selesai": "09:40",
            "ruangan_kode": "A101",
            "dosen_id": sample_entities["dosen"][0].id,
        },
    )
    assert r.status_code == 404


def test_delete_jadwal_204_lalu_404(
    client: TestClient, jadwal_a101: Jadwal
) -> None:
    r1 = client.delete(f"/api/jadwal/{jadwal_a101.id}")
    assert r1.status_code == 204

    r2 = client.delete(f"/api/jadwal/{jadwal_a101.id}")
    assert r2.status_code == 404


def test_get_conflicts_melaporkan_data_impor_bentrok(
    client: TestClient, db_session: Session, sample_entities: dict, jadwal_a101: Jadwal
) -> None:
    """Simulasi data legacy/impor yang masuk langsung ke DB tanpa lewat service."""
    impor_bentrok = Jadwal(
        kelas_id=sample_entities["kelas"]["stat_b"].id,
        hari=1,
        jam_mulai=time(8, 30),
        jam_selesai=time(10, 0),
        ruangan_kode="A101",
        dosen_id=sample_entities["dosen"][1].id,
    )
    db_session.add(impor_bentrok)
    db_session.commit()

    r = client.get("/api/jadwal/conflicts")
    assert r.status_code == 200
    conflicts = r.json()
    assert len(conflicts) == 1
    assert conflicts[0]["type"] == "room_conflict"
    assert conflicts[0]["affected"] == sorted([jadwal_a101.id, impor_bentrok.id])


def test_seed_data_memenuhi_target_minimal(
    client: TestClient, db_session: Session
) -> None:
    """Verifikasi checklist seed: >=10 ruangan, >=15 dosen, >=40 jadwal, ada konflik sengaja."""
    ringkasan = seed_database(db_session, reset=True)
    assert ringkasan["ruangan"] >= 10
    assert ringkasan["dosen"] >= 15
    assert ringkasan["jadwal"] >= 40
    assert ringkasan["konflik"] >= 3

    r = client.get("/api/jadwal/conflicts")
    assert r.status_code == 200
    types = {c["type"] for c in r.json()}
    assert types == {"room_conflict", "lecturer_conflict"}


def test_alembic_migration_upgrade_dan_downgrade(tmp_path: Path) -> None:
    """Verifikasi migrasi Alembic 001 -> 002 -> downgrade 001 -> upgrade 002."""
    project_root = Path(__file__).resolve().parent.parent
    db_file = tmp_path / "test_migration.db"
    alembic_cfg = Config(str(project_root / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(project_root / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_file.as_posix()}")

    command.upgrade(alembic_cfg, "head")

    eng = create_engine(f"sqlite:///{db_file.as_posix()}")
    insp = inspect(eng)
    tables = set(insp.get_table_names())
    assert {"ruangan", "dosen", "kelas", "jadwal", "matakuliah", "krs", "krs_detail"} <= tables

    jadwal_indexes = {idx["name"] for idx in insp.get_indexes("jadwal")}
    assert {"ix_jadwal_ruangan", "ix_jadwal_dosen"} <= jadwal_indexes

    krs_detail_cols = {c["name"] for c in insp.get_columns("krs_detail")}
    assert "kelas_id" in krs_detail_cols

    mk_cols = {c["name"] for c in insp.get_columns("matakuliah")}
    assert {"hari", "jam_mulai", "jam_selesai"}.isdisjoint(mk_cols)
    eng.dispose()

    # Uji downgrade 1 langkah lalu upgrade kembali
    command.downgrade(alembic_cfg, "-1")
    eng_down = create_engine(f"sqlite:///{db_file.as_posix()}")
    insp_down = inspect(eng_down)
    assert "jadwal" not in set(insp_down.get_table_names())
    mk_cols_down = {c["name"] for c in insp_down.get_columns("matakuliah")}
    assert {"hari", "jam_mulai", "jam_selesai"} <= mk_cols_down
    eng_down.dispose()

    command.upgrade(alembic_cfg, "head")
