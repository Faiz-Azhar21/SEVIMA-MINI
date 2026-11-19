import os
import pytest
from alembic import command
from alembic.config import Config

def test_alembic_migrations():
    alembic_ini_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic.ini")
    alembic_cfg = Config(alembic_ini_path)

    # Test downgrade to base (rollback)
    try:
        command.downgrade(alembic_cfg, "base")
    except Exception as e:
        pytest.fail(f"Rollback downgrade failed: {e}")

    # Test upgrade to head
    try:
        command.upgrade(alembic_cfg, "head")
    except Exception as e:
        pytest.fail(f"Upgrade migration failed: {e}")

    # Test downgrade again to ensure clean rollback
    try:
        command.downgrade(alembic_cfg, "base")
        command.upgrade(alembic_cfg, "head")
    except Exception as e:
        pytest.fail(f"Repeated migration rollback/upgrade failed: {e}")
