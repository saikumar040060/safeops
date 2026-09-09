"""Readiness: verifies the things that must be true before this instance
should receive traffic. Deliberately public (no auth) -- an orchestrator's
health/readiness probe cannot authenticate, the same as /api/health.
Never returns secret values, only booleans/short status labels.
"""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db

router = APIRouter(tags=["health"])

_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"

_REQUIRED_TABLES = (
    "agents",
    "executions",
    "execution_steps",
    "approval_requests",
    "audit_events",
    "operators",
    "operator_tokens",
)


def _expected_head_revision() -> str | None:
    try:
        config = Config(str(_ALEMBIC_INI))
        script = ScriptDirectory.from_config(config)
        return script.get_current_head()
    except Exception:
        return None


@router.get("/ready")
def readiness(response: Response, db: Session = Depends(get_db)) -> dict:
    checks: dict[str, bool] = {}

    try:
        db.execute(text("SELECT 1"))
        checks["database_reachable"] = True
    except Exception:
        checks["database_reachable"] = False

    if checks["database_reachable"]:
        try:
            current = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
            expected = _expected_head_revision()
            checks["migrations_at_head"] = expected is not None and current == expected
        except Exception:
            checks["migrations_at_head"] = False

        try:
            for table in _REQUIRED_TABLES:
                db.execute(text(f"SELECT 1 FROM {table} LIMIT 1"))  # noqa: S608
            checks["required_tables_accessible"] = True
        except Exception:
            checks["required_tables_accessible"] = False
    else:
        checks["migrations_at_head"] = False
        checks["required_tables_accessible"] = False

    try:
        settings = get_settings()
        checks["configuration_valid"] = bool(settings.environment) and bool(settings.database_url)
    except Exception:
        checks["configuration_valid"] = False

    ready = all(checks.values())
    response.status_code = 200 if ready else 503
    return {"ready": ready, "checks": checks}
