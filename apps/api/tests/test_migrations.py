from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy import inspect

from alembic import command
from app.core.database import Base

API_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TABLES = {"agents", "tools", "executions", "audit_events", "approval_requests"}


@pytest.fixture()
def alembic_config(db_engine, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    return cfg


def test_upgrade_from_empty_database(alembic_config, db_engine):
    Base.metadata.drop_all(db_engine)
    with db_engine.connect() as conn:
        conn.execute(sa.text("DROP TABLE IF EXISTS alembic_version"))
        conn.commit()

    command.upgrade(alembic_config, "head")

    tables = set(inspect(db_engine).get_table_names())
    assert EXPECTED_TABLES.issubset(tables)


def test_downgrade_to_base_then_restore(alembic_config, db_engine):
    command.downgrade(alembic_config, "base")
    tables = set(inspect(db_engine).get_table_names())
    assert not (EXPECTED_TABLES & tables)

    # Leave the schema at head so other tests/fixtures relying on it still work.
    command.upgrade(alembic_config, "head")
    tables = set(inspect(db_engine).get_table_names())
    assert EXPECTED_TABLES.issubset(tables)
