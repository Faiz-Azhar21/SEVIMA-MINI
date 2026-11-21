"""Verifikasi migrasi Alembic (0001 -> 0002 -> 0001 -> 0002) berjalan mulus di SQLite."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from app.database import create_db_engine


def test_alembic_upgrade_dan_downgrade(tmp_path: Path, monkeypatch) -> None:
    db_file = tmp_path / "alembic_test.db"
    db_url = f"sqlite:///{db_file}"
    monkeypatch.setenv("DATABASE_URL", db_url)

    project_root = Path(__file__).resolve().parent.parent
    alembic_cfg = Config(str(project_root / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(project_root / "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    # 1. Upgrade ke baseline M5-M8 lalu isi skala_nilai awal
    command.upgrade(alembic_cfg, "0001_baseline_m5_m8")
    engine = create_db_engine(db_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO skala_nilai (huruf, bobot) VALUES "
                "('A', 4.0), ('B', 3.0), ('C', 2.0), ('D', 1.0), ('E', 0.0)"
            )
        )

    # 2. Upgrade ke head (Minggu 9)
    command.upgrade(alembic_cfg, "head")
    insp = inspect(engine)
    assert "grade_history" in insp.get_table_names()

    skala_cols = {c["name"] for c in insp.get_columns("skala_nilai")}
    assert {"huruf", "bobot", "lulus"} <= skala_cols

    fks_krs_detail = insp.get_foreign_keys("krs_detail")
    assert any(
        fk["referred_table"] == "skala_nilai" and fk["constrained_columns"] == ["nilai"]
        for fk in fks_krs_detail
    )

    with engine.connect() as conn:
        # Pastikan A, B, C berstatus lulus=1 dan D, E lulus=0
        rows = dict(conn.execute(text("SELECT huruf, lulus FROM skala_nilai")).all())
        assert rows == {"A": 1, "B": 1, "C": 1, "D": 0, "E": 0}
        # Pastikan view v_riwayat_nilai dapat di-query
        assert conn.execute(text("SELECT * FROM v_riwayat_nilai")).all() == []

    # 3. Downgrade kembali ke baseline lalu upgrade lagi ke head (reversibility check)
    command.downgrade(alembic_cfg, "0001_baseline_m5_m8")
    insp_after_down = inspect(engine)
    assert "grade_history" not in insp_after_down.get_table_names()
    assert "lulus" not in {c["name"] for c in insp_after_down.get_columns("skala_nilai")}

    command.upgrade(alembic_cfg, "head")
    assert "grade_history" in inspect(engine).get_table_names()
    engine.dispose()
