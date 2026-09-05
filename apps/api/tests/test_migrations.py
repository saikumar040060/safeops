import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from alembic import command
from app.core.database import Base
from app.core.seed import seed
from app.models import Agent, ApprovalRequest, Execution
from app.models.enums import ExecutionStatus
from app.services.approval_engine import ApprovalEngine
from app.services.tool_gateway import ToolGateway

API_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TABLES = {
    "agents",
    "tools",
    "executions",
    "audit_events",
    "approval_requests",
    "customers",
    "payments",
    "refunds",
    "support_tickets",
    "services",
    "deployments",
    "service_logs",
    "agent_tool_permissions",
    "tool_requests",
    "policies",
    "policy_decisions",
}
EXPECTED_CHECKS = {
    "agents": {
        "agentstatus": {"ACTIVE", "DISABLED"},
        "risklevel": {"LOW", "MEDIUM", "HIGH", "CRITICAL"},
    },
    "tools": {"risklevel": {"LOW", "MEDIUM", "HIGH", "CRITICAL"}},
    "executions": {
        "executionstatus": {"RUNNING", "WAITING_APPROVAL", "COMPLETED", "FAILED", "BLOCKED"}
    },
    "approval_requests": {
        "approvalstatus": {"PENDING", "APPROVED", "REJECTED", "EXPIRED", "EXECUTED"},
        "risklevel": {"LOW", "MEDIUM", "HIGH", "CRITICAL"},
    },
    "audit_events": {
        "auditeventtype": {
            "EXECUTION_STARTED",
            "AGENT_REASONED",
            "TOOL_REQUESTED",
            "PERMISSION_CHECKED",
            "POLICY_CHECKED",
            "POLICY_EVALUATION_REQUIRED",
            "POLICY_EVALUATION_STARTED",
            "POLICY_MATCHED",
            "POLICY_ALLOWED",
            "POLICY_APPROVAL_REQUIRED",
            "POLICY_BLOCKED",
            "RISK_ASSESSED",
            "ACTION_ALLOWED",
            "ACTION_DENIED",
            "ACTION_BLOCKED",
            "APPROVAL_REQUESTED",
            "APPROVAL_GRANTED",
            "APPROVAL_APPROVED",
            "APPROVAL_REJECTED",
            "APPROVAL_EXPIRED",
            "APPROVED_ACTION_EXECUTION_STARTED",
            "APPROVED_ACTION_EXECUTED",
            "APPROVED_ACTION_FAILED",
            "TOOL_EXECUTED",
            "TOOL_FAILED",
            "SECURITY_INCIDENT",
            "EXECUTION_COMPLETED",
        }
    },
    "payments": {"paymentstatus": {"SUCCEEDED", "REFUNDED"}},
    "deployments": {"deploymentenvironment": {"STAGING", "PRODUCTION"}},
    "service_logs": {"loglevel": {"INFO", "WARN", "ERROR"}},
    "agent_tool_permissions": {"permissiontype": {"ALLOW", "DENY", "CONDITIONAL"}},
    "tool_requests": {
        "toolrequeststatus": {"REQUESTED", "EXECUTED", "DENIED", "FAILED", "REQUIRES_APPROVAL"}
    },
    "policies": {"policyaction": {"ALLOW", "REQUIRE_APPROVAL", "BLOCK"}},
    "policy_decisions": {"policyaction": {"ALLOW", "REQUIRE_APPROVAL", "BLOCK"}},
}


@pytest.fixture()
def alembic_config(db_engine, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", db_engine.url.render_as_string(hide_password=False))
    cfg = Config(str(API_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_ROOT / "alembic"))
    return cfg


def _reset_to_empty(alembic_config, db_engine) -> None:
    Base.metadata.drop_all(db_engine)
    with db_engine.connect() as conn:
        conn.execute(sa.text("DROP TABLE IF EXISTS alembic_version"))
        conn.commit()


def test_upgrade_from_empty_database(alembic_config, db_engine):
    _reset_to_empty(alembic_config, db_engine)
    command.upgrade(alembic_config, "head")

    tables = set(inspect(db_engine).get_table_names())
    assert EXPECTED_TABLES.issubset(tables)

    inspector = inspect(db_engine)
    for table, expected_checks in EXPECTED_CHECKS.items():
        checks = {
            check["name"]: check["sqltext"]
            for check in inspector.get_check_constraints(table)
        }
        assert checks.keys() == expected_checks.keys()
        for name, values in expected_checks.items():
            assert all(f"'{value}'" in checks[name] for value in values)

    unique_constraints = inspector.get_unique_constraints("audit_events")
    assert any(
        constraint["name"] == "uq_audit_events_execution_sequence"
        and constraint["column_names"] == ["execution_id", "sequence"]
        for constraint in unique_constraints
    )

    for table in (
        "executions",
        "audit_events",
        "approval_requests",
        "agent_tool_permissions",
        "tool_requests",
        "policies",
        "policy_decisions",
    ):
        foreign_keys = inspector.get_foreign_keys(table)
        assert all(fk["options"].get("ondelete") is None for fk in foreign_keys)

    unique_constraints = inspector.get_unique_constraints("policies")
    assert any(
        constraint["name"] == "uq_policies_policy_key"
        and constraint["column_names"] == ["policy_key"]
        for constraint in unique_constraints
    )


def test_downgrade_to_base_then_restore(alembic_config, db_engine):
    _reset_to_empty(alembic_config, db_engine)
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "base")
    tables = set(inspect(db_engine).get_table_names())
    assert not (EXPECTED_TABLES & tables)

    # Leave the schema at head so other tests/fixtures relying on it still work.
    command.upgrade(alembic_config, "head")
    tables = set(inspect(db_engine).get_table_names())
    assert EXPECTED_TABLES.issubset(tables)


def test_approval_migration_round_trip_with_resolved_rows(alembic_config, db_engine):
    _reset_to_empty(alembic_config, db_engine)
    command.upgrade(alembic_config, "head")

    gateway = ToolGateway()
    approval_engine = ApprovalEngine()
    with Session(db_engine) as session:
        seed(session)
        agent = session.query(Agent).filter_by(name="support-agent").one()

        approval_ids = []
        for suffix in ("approved", "rejected"):
            execution = Execution(
                agent_id=agent.id,
                objective=f"migration {suffix}",
                status=ExecutionStatus.RUNNING,
            )
            session.add(execution)
            session.commit()
            result = gateway.execute(
                agent_id=agent.id,
                execution_id=execution.id,
                tool_name="refund_payment",
                arguments={
                    "payment_id": "PAY-9003",
                    "amount": "750.00",
                    "reason": "migration round trip",
                    "idempotency_key": f"migration-{suffix}-{uuid.uuid4()}",
                },
                db=session,
            )
            approval_ids.append(uuid.UUID(result.approval_request_id))

        approved = approval_engine.approve(
            approval_id=approval_ids[0], resolved_by="migration-review", db=session
        )
        rejected = approval_engine.reject(
            approval_id=approval_ids[1],
            resolved_by="migration-review",
            reason="migration rejection",
            db=session,
        )
        assert approved.status == "EXECUTED"
        assert rejected.status == "REJECTED"
        assert session.query(ApprovalRequest).count() == 2

    command.downgrade(alembic_config, "92c9d30a5b8d")
    with db_engine.connect() as connection:
        count = connection.execute(sa.text("SELECT count(*) FROM approval_requests")).scalar()
        assert count == 0

    command.upgrade(alembic_config, "head")
    approval_columns = {
        column["name"] for column in inspect(db_engine).get_columns("approval_requests")
    }
    assert {
        "tool_request_id",
        "policy_decision_id",
        "approved_arguments",
        "expires_at",
        "executed_at",
    }.issubset(approval_columns)
