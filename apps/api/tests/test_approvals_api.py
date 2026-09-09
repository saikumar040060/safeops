import uuid

from sqlalchemy import select

from app.models import Agent, ApprovalRequest, AuditEvent, Operator
from app.models.enums import AuditEventType
from app.services.agent_runtime import AgentRuntime

runtime = AgentRuntime()

APPROVER_TOKEN = "sfops_demo_approver_signoff"
_APPROVER_HEADERS = {"Authorization": f"Bearer {APPROVER_TOKEN}"}


def _agent(db, name) -> Agent:
    return db.query(Agent).filter_by(name=name).one()


def _pending_refund_approval(db):
    agent = _agent(db, "support-agent")
    start = runtime.start_execution(
        agent_id=agent.id,
        objective="Investigate duplicate payment for CUST-1001 and refund the duplicate",
        db=db,
    )
    execution_id = uuid.UUID(start.execution_id)
    runtime.step(execution_id, db)
    runtime.step(execution_id, db)
    return runtime.step(execution_id, db)


def test_approval_listing_shows_pending_request(client, seeded_db):
    result = _pending_refund_approval(seeded_db)

    response = client.get("/api/approvals", headers=_APPROVER_HEADERS)
    assert response.status_code == 200
    approvals = response.json()
    assert len(approvals) == 1
    approval = approvals[0]
    assert approval["id"] == result.approval_request_id
    assert approval["tool_name"] == "refund_payment"
    assert approval["status"] == "PENDING"
    assert approval["approved_arguments"]["payment_id"] == "PAY-9002"


def test_approval_listing_requires_authentication(client):
    assert client.get("/api/approvals").status_code == 401


def test_approval_detail_unknown_id_returns_404(client):
    response = client.get(f"/api/approvals/{uuid.uuid4()}", headers=_APPROVER_HEADERS)
    assert response.status_code == 404


def test_approve_endpoint_ignores_extra_argument_fields(client, seeded_db):
    # The API only ever accepts resolver identity metadata -- posting extra
    # fields (as a hostile client trying to smuggle replacement arguments
    # would) must have no effect on what actually executes.
    result = _pending_refund_approval(seeded_db)

    response = client.post(
        f"/api/approvals/{result.approval_request_id}/approve",
        json={
            "resolved_by": "alice",
            "arguments": {"payment_id": "PAY-EVIL", "amount": "999999.00"},
        },
        headers=_APPROVER_HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["tool_result"]["payment_id"] == "PAY-9002"
    assert body["tool_result"]["refund_amount"] == "750.00"


def test_approve_endpoint_ignores_spoofed_resolved_by(client, seeded_db):
    # A caller-supplied `resolved_by` must never override the identity
    # derived from the authenticated bearer token.
    result = _pending_refund_approval(seeded_db)

    response = client.post(
        f"/api/approvals/{result.approval_request_id}/approve",
        json={"resolved_by": "attacker-spoofed-name"},
        headers=_APPROVER_HEADERS,
    )
    assert response.status_code == 200

    approval = seeded_db.get(ApprovalRequest, uuid.UUID(result.approval_request_id))
    seeded_db.refresh(approval)
    assert approval.resolved_by == "approver-demo"
    assert approval.resolved_by != "attacker-spoofed-name"

    approved_event = seeded_db.scalar(
        select(AuditEvent).where(
            AuditEvent.execution_id == approval.execution_id,
            AuditEvent.event_type == AuditEventType.APPROVAL_APPROVED,
        )
    )
    approver = seeded_db.query(Operator).filter_by(username="approver-demo").one()
    assert approved_event.event_metadata["actor_id"] == str(approver.id)
    assert approved_event.event_metadata["actor_type"] == "operator"


def test_reject_endpoint(client, seeded_db):
    result = _pending_refund_approval(seeded_db)

    response = client.post(
        f"/api/approvals/{result.approval_request_id}/reject",
        json={"resolved_by": "bob", "reason": "not authorized"},
        headers=_APPROVER_HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "REJECTED"
