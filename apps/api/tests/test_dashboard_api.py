import uuid

from app.models import Agent, Execution
from app.models.enums import ExecutionStatus
from app.services.agent_runtime import AgentRuntime
from app.services.approval_engine import ApprovalEngine

runtime = AgentRuntime()
approval_engine = ApprovalEngine()


def test_dashboard_summary_empty_baseline(viewer_client):
    response = viewer_client.get("/api/dashboard/summary")
    assert response.status_code == 200
    body = response.json()
    metrics = body["metrics"]
    assert metrics["active_executions"] == 0
    assert metrics["waiting_approvals"] == 0
    assert metrics["blocked_actions"] == 0
    assert metrics["open_security_incidents"] == 0
    assert metrics["completed_executions"] == 0
    assert metrics["risk_assessments_by_severity"] == []
    assert body["recent_executions"] == []
    assert body["recent_approvals"] == []
    assert body["recent_incidents"] == []
    assert body["recent_blocked"] == []


def test_dashboard_summary_reflects_real_backend_state(viewer_client, seeded_db):
    agent = seeded_db.query(Agent).filter_by(name="support-agent").one()

    start = runtime.start_execution(agent_id=agent.id, objective="test objective", db=seeded_db)
    running_execution_id = uuid.UUID(start.execution_id)

    completed_execution = Execution(
        agent_id=agent.id, objective="done", status=ExecutionStatus.COMPLETED
    )
    seeded_db.add(completed_execution)
    seeded_db.commit()

    response = viewer_client.get("/api/dashboard/summary")
    assert response.status_code == 200
    metrics = response.json()["metrics"]
    assert metrics["active_executions"] == 1
    assert metrics["completed_executions"] == 1

    execution_ids = {e["id"] for e in response.json()["recent_executions"]}
    assert str(running_execution_id) in execution_ids
    assert str(completed_execution.id) in execution_ids


def test_dashboard_summary_counts_pending_approval(viewer_client, seeded_db):
    agent = seeded_db.query(Agent).filter_by(name="support-agent").one()
    start = runtime.start_execution(
        agent_id=agent.id,
        objective="Investigate duplicate payment for CUST-1001 and refund the duplicate",
        db=seeded_db,
    )
    execution_id = uuid.UUID(start.execution_id)
    runtime.step(execution_id, seeded_db)
    runtime.step(execution_id, seeded_db)
    result = runtime.step(execution_id, seeded_db)
    assert result.status == "WAITING_APPROVAL"

    response = viewer_client.get("/api/dashboard/summary")
    metrics = response.json()["metrics"]
    assert metrics["waiting_approvals"] == 1
    assert any(a["id"] == result.approval_request_id for a in response.json()["recent_approvals"])
