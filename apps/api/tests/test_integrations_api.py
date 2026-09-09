"""HTTP-level smoke tests for the generic external-integration API. The
full security checklist (auth/scope/mapping/idempotency/approval/block/
concurrency) lives in test_integrations_security.py; this file just
confirms the wire-level plumbing (routes -> service -> AgentRuntime ->
ToolGateway) actually works end to end through real HTTP requests."""

import uuid

INTEGRATION_TOKEN = "sfops_demo_integration_support"


def _auth(token: str = INTEGRATION_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _support_agent_id(db) -> str:
    from app.models import Agent

    return str(db.query(Agent).filter_by(name="support-agent").one().id)


def test_list_tools_returns_discoverable_tools_only(client, seeded_db):
    agent_id = _support_agent_id(seeded_db)
    resp = client.get(f"/api/integrations/tools?safeops_agent_id={agent_id}", headers=_auth())
    assert resp.status_code == 200
    names = {t["name"] for t in resp.json()}
    assert "read_customer" in names
    assert "get_payments" in names
    # support-agent is DENY on these -- must not be discoverable.
    assert "deploy_production" not in names
    assert "deploy_staging" not in names
    assert "read_logs" not in names


def test_submit_allow_action_executes(client, seeded_db):
    agent_id = _support_agent_id(seeded_db)
    resp = client.post(
        "/api/integrations/actions",
        json={
            "external_request_id": str(uuid.uuid4()),
            "safeops_agent_id": agent_id,
            "tool_name": "read_customer",
            "arguments": {"customer_id": "CUST-1001"},
            "objective": "external read_customer smoke test",
        },
        headers=_auth(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "EXECUTED"
    assert body["result"]["customer_id"] == "CUST-1001"


def test_submit_requires_approval_action_pauses(client, seeded_db):
    agent_id = _support_agent_id(seeded_db)
    external_request_id = str(uuid.uuid4())
    resp = client.post(
        "/api/integrations/actions",
        json={
            "external_request_id": external_request_id,
            "safeops_agent_id": agent_id,
            "tool_name": "refund_payment",
            "arguments": {
                "payment_id": "PAY-9002",
                "amount": "750.00",
                "reason": "external refund smoke test",
                "idempotency_key": f"http-{external_request_id}",
            },
            "objective": "external refund smoke test",
        },
        headers=_auth(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "REQUIRES_APPROVAL"
    assert body["approval_request_id"] is not None

    status_resp = client.get(f"/api/integrations/actions/{external_request_id}", headers=_auth())
    assert status_resp.status_code == 200
    assert status_resp.json()["status"] == "WAITING_APPROVAL"


def test_idempotent_retry_returns_same_result(client, seeded_db):
    agent_id = _support_agent_id(seeded_db)
    external_request_id = str(uuid.uuid4())
    body = {
        "external_request_id": external_request_id,
        "safeops_agent_id": agent_id,
        "tool_name": "read_customer",
        "arguments": {"customer_id": "CUST-1001"},
    }
    first = client.post("/api/integrations/actions", json=body, headers=_auth())
    second = client.post("/api/integrations/actions", json=body, headers=_auth())
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["result"] == second.json()["result"]


def test_conflicting_payload_same_key_is_rejected(client, seeded_db):
    agent_id = _support_agent_id(seeded_db)
    external_request_id = str(uuid.uuid4())
    client.post(
        "/api/integrations/actions",
        json={
            "external_request_id": external_request_id,
            "safeops_agent_id": agent_id,
            "tool_name": "read_customer",
            "arguments": {"customer_id": "CUST-1001"},
        },
        headers=_auth(),
    )
    resp = client.post(
        "/api/integrations/actions",
        json={
            "external_request_id": external_request_id,
            "safeops_agent_id": agent_id,
            "tool_name": "read_customer",
            "arguments": {"customer_id": "CUST-9999"},
        },
        headers=_auth(),
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "IDEMPOTENCY_CONFLICT"
