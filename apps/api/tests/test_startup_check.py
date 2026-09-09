"""Regression test for a Milestone 10 review finding: under
`uvicorn --workers N`, a config-validation failure at app.main import time
crashed inside every worker independently, and uvicorn's multiprocess
supervisor kept respawning workers forever instead of the container
exiting -- an indefinite crash loop rather than a clean, single startup
failure. app/core/startup_check.py is meant to run once, before uvicorn
starts any worker (see infra/docker/api.Dockerfile's production CMD)."""

from app.core.config import Settings
from app.core.startup_check import main


def test_startup_check_exits_zero_for_safe_config(monkeypatch):
    safe = Settings(
        environment="production",
        demo_mode=False,
        database_url="postgresql+psycopg2://real:real@prod-db.internal:5432/safeops",
        cors_origins=["https://ops.example.com"],
        bootstrap_admin_token="a" * 40,
    )
    monkeypatch.setattr("app.core.startup_check.get_settings", lambda: safe)
    assert main() == 0


def test_startup_check_exits_nonzero_for_unsafe_config(monkeypatch, capsys):
    unsafe = Settings(
        environment="production",
        demo_mode=True,
        database_url="postgresql+psycopg2://real:real@prod-db.internal:5432/safeops",
        cors_origins=["https://ops.example.com"],
        bootstrap_admin_token="a" * 40,
    )
    monkeypatch.setattr("app.core.startup_check.get_settings", lambda: unsafe)
    assert main() == 1
    assert "STARTUP CHECK FAILED" in capsys.readouterr().err


def test_startup_check_is_a_no_op_for_development():
    # development settings must never fail this check regardless of flags
    # -- validate_production_safety() itself is a no-op outside production.
    dev = Settings(environment="development", demo_mode=True)
    from app.core.config import validate_production_safety

    validate_production_safety(dev)  # must not raise
