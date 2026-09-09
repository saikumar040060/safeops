"""Section 19 role matrix: unauthenticated/each-role behavior against the
approve endpoint (the most security-critical one) plus spot checks that
read/execute gates are wired the same way everywhere else."""

import uuid

from app.models import Agent
from app.services.agent_runtime import AgentRuntime

runtime = AgentRuntime()

TOKENS = {
    "VIEWER": "sfops_demo_viewer_readonly",
    "OPERATOR": "sfops_demo_operator_runexec",
    "APPROVER": "sfops_demo_approver_signoff",
    "ADMIN": "sfops_demo_admin_allaccess",
}


def _headers(role: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKENS[role]}"}


def _pending_refund_approval(db):
    agent = db.query(Agent).filter_by(name="support-agent").one()
    start = runtime.start_execution(
        agent_id=agent.id,
        objective="Investigate duplicate payment for CUST-1001 and refund the duplicate",
        db=db,
    )
    execution_id = uuid.UUID(start.execution_id)
    runtime.step(execution_id, db)
    runtime.step(execution_id, db)
    return runtime.step(execution_id, db)


def test_unauthenticated_approval_is_rejected(client, seeded_db):
    result = _pending_refund_approval(seeded_db)
    resp = client.post(f"/api/approvals/{result.approval_request_id}/approve", json={})
    assert resp.status_code == 401


def test_viewer_cannot_approve(client, seeded_db):
    result = _pending_refund_approval(seeded_db)
    resp = client.post(
        f"/api/approvals/{result.approval_request_id}/approve",
        json={},
        headers=_headers("VIEWER"),
    )
    assert resp.status_code == 403


def test_operator_cannot_approve(client, seeded_db):
    result = _pending_refund_approval(seeded_db)
    resp = client.post(
        f"/api/approvals/{result.approval_request_id}/approve",
        json={},
        headers=_headers("OPERATOR"),
    )
    assert resp.status_code == 403


def test_approver_can_approve(client, seeded_db):
    result = _pending_refund_approval(seeded_db)
    resp = client.post(
        f"/api/approvals/{result.approval_request_id}/approve",
        json={},
        headers=_headers("APPROVER"),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "EXECUTED"


def test_admin_can_approve(client, seeded_db):
    result = _pending_refund_approval(seeded_db)
    resp = client.post(
        f"/api/approvals/{result.approval_request_id}/approve",
        json={},
        headers=_headers("ADMIN"),
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "EXECUTED"


def test_viewer_cannot_start_execution(client, seeded_db):
    agent = seeded_db.query(Agent).filter_by(name="support-agent").one()
    resp = client.post(
        "/api/executions",
        json={
            "agent_id": str(agent.id),
            "objective": "Deploy checkout-service version 1.0 to staging",
        },
        headers=_headers("VIEWER"),
    )
    assert resp.status_code == 403


def test_operator_can_start_execution(client, seeded_db):
    agent = seeded_db.query(Agent).filter_by(name="devops-agent").one()
    resp = client.post(
        "/api/executions",
        json={
            "agent_id": str(agent.id),
            "objective": "Deploy checkout-service version 1.0 to staging",
        },
        headers=_headers("OPERATOR"),
    )
    assert resp.status_code == 200


def test_approver_cannot_start_execution(client, seeded_db):
    agent = seeded_db.query(Agent).filter_by(name="devops-agent").one()
    resp = client.post(
        "/api/executions",
        json={
            "agent_id": str(agent.id),
            "objective": "Deploy checkout-service version 1.0 to staging",
        },
        headers=_headers("APPROVER"),
    )
    assert resp.status_code == 403


def test_every_role_can_read(client, seeded_db):
    for role in TOKENS:
        resp = client.get("/api/agents", headers=_headers(role))
        assert resp.status_code == 200, role


def test_invalid_token_rejected_safely_with_no_detail_leak(client):
    resp = client.get("/api/agents", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401
    body = resp.json()
    assert "not-a-real-token" not in str(body)
    assert body["detail"]["code"] == "UNAUTHENTICATED"


def test_malformed_auth_header_rejected_safely(client):
    for header in ["Bearer", "", "Basic dXNlcjpwYXNz", "Bearer "]:
        resp = client.get("/api/agents", headers={"Authorization": header})
        assert resp.status_code == 401
