import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Agent,
    ApprovalRequest,
    AuditEvent,
    Deployment,
    Execution,
    Payment,
    Service,
    ToolRequest,
)
from app.models.enums import AuditEventType, ExecutionStatus, PaymentStatus, ToolRequestStatus
from app.services.approval_engine import ApprovalEngine
from app.services.tool_gateway import ToolGateway

gateway = ToolGateway()
approval_engine = ApprovalEngine()


def _agent(db, name) -> Agent:
    return db.query(Agent).filter_by(name=name).one()


def _make_execution(db, agent, status=ExecutionStatus.RUNNING) -> Execution:
    execution = Execution(agent_id=agent.id, objective="test objective", status=status)
    db.add(execution)
    db.commit()
    db.refresh(execution)
    return execution


def _events(db, execution_id):
    return (
        db.query(AuditEvent)
        .filter_by(execution_id=execution_id)
        .order_by(AuditEvent.sequence)
        .all()
    )


def _request_refund_approval(db, agent=None, execution=None, amount="750.00", idem=None):
    agent = agent or _agent(db, "support-agent")
    execution = execution or _make_execution(db, agent)
    idem = idem or f"gw-{uuid.uuid4()}"
    result = gateway.execute(
        agent_id=agent.id,
        execution_id=execution.id,
        tool_name="refund_payment",
        arguments={
            "payment_id": "PAY-9003",
            "amount": amount,
            "reason": "Duplicate transaction",
            "idempotency_key": idem,
        },
        db=db,
    )
    return result, execution


def test_require_approval_creates_approval_request(seeded_db):
    result, execution = _request_refund_approval(seeded_db)

    assert result.status == "REQUIRES_APPROVAL"
    assert result.approval_request_id is not None
    approval = seeded_db.get(ApprovalRequest, uuid.UUID(result.approval_request_id))
    assert approval is not None
    assert approval.status.value == "PENDING"
    assert approval.tool_name == "refund_payment"

    execution_row = seeded_db.get(Execution, execution.id)
    assert execution_row.status == ExecutionStatus.WAITING_APPROVAL


def test_require_approval_reapplies_execution_state_after_audit_retry(seeded_db, monkeypatch):
    agent = _agent(seeded_db, "support-agent")
    execution = _make_execution(seeded_db, agent)
    original_commit = seeded_db.commit
    collision_raised = False

    class SequenceCollision(Exception):
        class diag:
            constraint_name = "uq_audit_events_execution_sequence"

    def collide_once():
        nonlocal collision_raised
        has_new_approval = any(isinstance(row, ApprovalRequest) for row in seeded_db.new)
        if has_new_approval and not collision_raised:
            collision_raised = True
            raise IntegrityError(None, None, SequenceCollision())
        original_commit()

    monkeypatch.setattr(seeded_db, "commit", collide_once)
    result, _ = _request_refund_approval(seeded_db, agent=agent, execution=execution)

    assert collision_raised is True
    assert result.status == "REQUIRES_APPROVAL"
    seeded_db.refresh(execution)
    assert execution.status == ExecutionStatus.WAITING_APPROVAL


def test_stored_arguments_match_original_request(seeded_db):
    result, _ = _request_refund_approval(seeded_db, amount="750.00")
    approval = seeded_db.get(ApprovalRequest, uuid.UUID(result.approval_request_id))

    assert approval.approved_arguments["amount"] == "750.00"
    assert approval.approved_arguments["payment_id"] == "PAY-9003"


def test_modified_agent_arguments_cannot_affect_approved_action(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    execution = _make_execution(seeded_db, agent)
    original_args = {
        "payment_id": "PAY-9003",
        "amount": "750.00",
        "reason": "Duplicate transaction",
        "idempotency_key": f"gw-{uuid.uuid4()}",
    }
    result = gateway.execute(
        agent_id=agent.id,
        execution_id=execution.id,
        tool_name="refund_payment",
        arguments=original_args,
        db=seeded_db,
    )

    # Simulate the agent trying to change its mind after the fact.
    original_args["amount"] = "1.00"
    original_args["payment_id"] = "PAY-9001"

    approve_result = approval_engine.approve(
        approval_id=uuid.UUID(result.approval_request_id), resolved_by="alice", db=seeded_db
    )

    assert approve_result.status == "EXECUTED"
    assert approve_result.tool_result["payment_id"] == "PAY-9003"
    assert approve_result.tool_result["refund_amount"] == "750.00"


def test_approval_executes_original_action_exactly_once(seeded_db):
    result, execution = _request_refund_approval(seeded_db, amount="750.00")

    approve_result = approval_engine.approve(
        approval_id=uuid.UUID(result.approval_request_id), resolved_by="alice", db=seeded_db
    )

    assert approve_result.status == "EXECUTED"
    payment = seeded_db.query(Payment).filter_by(payment_id="PAY-9003").one()
    assert payment.status.value == "REFUNDED"

    tool_request = seeded_db.query(ToolRequest).filter_by(execution_id=execution.id).one()
    assert tool_request.status.value == "EXECUTED"
    assert tool_request.completed_at is not None

    approval = seeded_db.get(ApprovalRequest, uuid.UUID(result.approval_request_id))
    assert approval.status.value == "EXECUTED"
    assert approval.executed_at is not None

    execution_row = seeded_db.get(Execution, execution.id)
    assert execution_row.status == ExecutionStatus.RUNNING


def test_reject_causes_zero_side_effects(seeded_db):
    result, execution = _request_refund_approval(seeded_db, amount="750.00")

    reject_result = approval_engine.reject(
        approval_id=uuid.UUID(result.approval_request_id),
        resolved_by="bob",
        reason="Looks fraudulent",
        db=seeded_db,
    )

    assert reject_result.status == "REJECTED"
    payment = seeded_db.query(Payment).filter_by(payment_id="PAY-9003").one()
    assert payment.status.value == "SUCCEEDED"  # untouched

    tool_request = seeded_db.query(ToolRequest).filter_by(execution_id=execution.id).one()
    assert tool_request.status.value == "DENIED"

    approval = seeded_db.get(ApprovalRequest, uuid.UUID(result.approval_request_id))
    assert approval.status.value == "REJECTED"

    execution_row = seeded_db.get(Execution, execution.id)
    assert execution_row.status == ExecutionStatus.RUNNING


def test_rejection_reapplies_state_after_audit_retry(seeded_db, monkeypatch):
    result, execution = _request_refund_approval(seeded_db)
    original_commit = seeded_db.commit
    collision_raised = False

    class SequenceCollision(Exception):
        class diag:
            constraint_name = "uq_audit_events_execution_sequence"

    def collide_once():
        nonlocal collision_raised
        has_rejection_event = any(
            isinstance(row, AuditEvent)
            and row.event_type == AuditEventType.APPROVAL_REJECTED
            for row in seeded_db.new
        )
        if has_rejection_event and not collision_raised:
            collision_raised = True
            raise IntegrityError(None, None, SequenceCollision())
        original_commit()

    monkeypatch.setattr(seeded_db, "commit", collide_once)
    reject_result = approval_engine.reject(
        approval_id=uuid.UUID(result.approval_request_id),
        resolved_by="bob",
        reason=None,
        db=seeded_db,
    )

    assert collision_raised is True
    assert reject_result.status == "REJECTED"
    tool_request = seeded_db.query(ToolRequest).filter_by(execution_id=execution.id).one()
    assert tool_request.status == ToolRequestStatus.DENIED
    seeded_db.refresh(execution)
    assert execution.status == ExecutionStatus.RUNNING


def test_expired_approval_cannot_execute(seeded_db):
    result, execution = _request_refund_approval(seeded_db)
    approval = seeded_db.get(ApprovalRequest, uuid.UUID(result.approval_request_id))
    approval.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    seeded_db.commit()

    approve_result = approval_engine.approve(
        approval_id=approval.id, resolved_by="alice", db=seeded_db
    )

    assert approve_result.status == "ALREADY_RESOLVED"
    assert approve_result.approval_status == "EXPIRED"

    seeded_db.refresh(approval)
    assert approval.status.value == "EXPIRED"
    tool_request = seeded_db.query(ToolRequest).filter_by(execution_id=execution.id).one()
    assert tool_request.status == ToolRequestStatus.DENIED
    assert tool_request.error["code"] == "APPROVAL_EXPIRED"
    seeded_db.refresh(execution)
    assert execution.status == ExecutionStatus.RUNNING
    payment = seeded_db.query(Payment).filter_by(payment_id="PAY-9003").one()
    assert payment.status.value == "SUCCEEDED"


def test_double_approve_executes_once(seeded_db):
    result, _ = _request_refund_approval(seeded_db)
    approval_id = uuid.UUID(result.approval_request_id)

    first = approval_engine.approve(approval_id=approval_id, resolved_by="alice", db=seeded_db)
    second = approval_engine.approve(approval_id=approval_id, resolved_by="alice", db=seeded_db)

    assert first.status == "EXECUTED"
    assert second.status == "ALREADY_RESOLVED"
    assert second.approval_status == "EXECUTED"

    refund_count = seeded_db.execute(
        text(
            "SELECT count(*) FROM refunds WHERE payment_id = "
            "(SELECT id FROM payments WHERE payment_id = 'PAY-9003')"
        )
    ).scalar()
    assert refund_count == 1


def test_concurrent_approve_attempts_execute_once(seeded_db, db_engine):
    result, execution = _request_refund_approval(seeded_db)
    approval_id = uuid.UUID(result.approval_request_id)

    from threading import Barrier

    barrier = Barrier(2)

    def call_approve():
        with Session(db_engine) as session:
            barrier.wait(timeout=5)
            return approval_engine.approve(
                approval_id=approval_id, resolved_by="concurrent", db=session
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: call_approve(), range(2)))

    statuses = sorted(r.status for r in results)
    assert statuses == ["ALREADY_RESOLVED", "EXECUTED"]

    payment = seeded_db.query(Payment).filter_by(payment_id="PAY-9003").one()
    assert payment.status.value == "REFUNDED"

    executed_requests = (
        seeded_db.query(ToolRequest)
        .filter_by(execution_id=execution.id, status=ToolRequestStatus.EXECUTED)
        .count()
    )
    assert executed_requests == 1


def test_concurrent_gateway_calls_create_only_one_approval(
    seeded_db, db_engine, monkeypatch
):
    agent = _agent(seeded_db, "support-agent")
    execution = _make_execution(seeded_db, agent)

    from threading import Barrier

    from app.services import tool_gateway as tool_gateway_module

    barrier = Barrier(2)
    original_evaluate = tool_gateway_module.policy_engine.evaluate

    def synchronized_evaluate(**kwargs):
        result = original_evaluate(**kwargs)
        barrier.wait(timeout=5)
        return result

    monkeypatch.setattr(tool_gateway_module.policy_engine, "evaluate", synchronized_evaluate)

    def call_gateway(index):
        with Session(db_engine) as session:
            return gateway.execute(
                agent_id=agent.id,
                execution_id=execution.id,
                tool_name="refund_payment",
                arguments={
                    "payment_id": "PAY-9003",
                    "amount": "750.00",
                    "reason": "concurrent approval request",
                    "idempotency_key": f"concurrent-gateway-{index}",
                },
                db=session,
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(call_gateway, range(2)))

    assert sorted(result.status for result in results) == ["FAILED", "REQUIRES_APPROVAL"]
    seeded_db.expire_all()
    assert seeded_db.query(ApprovalRequest).filter_by(execution_id=execution.id).count() == 1
    assert seeded_db.get(Execution, execution.id).status == ExecutionStatus.WAITING_APPROVAL


def test_approve_after_reject_fails(seeded_db):
    result, _ = _request_refund_approval(seeded_db)
    approval_id = uuid.UUID(result.approval_request_id)
    approval_engine.reject(approval_id=approval_id, resolved_by="bob", reason=None, db=seeded_db)

    approve_result = approval_engine.approve(
        approval_id=approval_id, resolved_by="alice", db=seeded_db
    )

    assert approve_result.status == "ALREADY_RESOLVED"
    assert approve_result.approval_status == "REJECTED"
    payment = seeded_db.query(Payment).filter_by(payment_id="PAY-9003").one()
    assert payment.status.value == "SUCCEEDED"


def test_reject_after_approve_fails(seeded_db):
    result, _ = _request_refund_approval(seeded_db)
    approval_id = uuid.UUID(result.approval_request_id)
    approval_engine.approve(approval_id=approval_id, resolved_by="alice", db=seeded_db)

    reject_result = approval_engine.reject(
        approval_id=approval_id, resolved_by="bob", reason=None, db=seeded_db
    )

    assert reject_result.status == "ALREADY_RESOLVED"
    assert reject_result.approval_status == "EXECUTED"


def test_approve_after_execution_fails_safely(seeded_db):
    result, _ = _request_refund_approval(seeded_db)
    approval_id = uuid.UUID(result.approval_request_id)
    approval_engine.approve(approval_id=approval_id, resolved_by="alice", db=seeded_db)

    second = approval_engine.approve(approval_id=approval_id, resolved_by="alice", db=seeded_db)

    assert second.status == "ALREADY_RESOLVED"
    refund_count = (
        seeded_db.query(ToolRequest).filter_by(status=ToolRequestStatus.EXECUTED).count()
    )
    assert refund_count >= 1  # sanity: didn't wipe state
    payment = seeded_db.query(Payment).filter_by(payment_id="PAY-9003").one()
    assert payment.status.value == "REFUNDED"


def test_missing_approval_fails_safely(seeded_db):
    result = approval_engine.approve(
        approval_id=uuid.uuid4(), resolved_by="alice", db=seeded_db
    )

    assert result.status == "NOT_FOUND"


def test_wrong_execution_relationship_fails_closed(seeded_db):
    result, execution = _request_refund_approval(seeded_db)
    approval = seeded_db.get(ApprovalRequest, uuid.UUID(result.approval_request_id))

    # Corrupt the linkage: point the approval at a tool_request that belongs
    # to a completely different execution.
    other_agent = _agent(seeded_db, "devops-agent")
    other_execution = _make_execution(seeded_db, other_agent)
    other_tool_request = ToolRequest(
        execution_id=other_execution.id,
        agent_id=other_agent.id,
        tool_id=None,
        tool_name="read_logs",
        arguments={},
        status=ToolRequestStatus.REQUESTED,
    )
    seeded_db.add(other_tool_request)
    seeded_db.commit()
    approval.tool_request_id = other_tool_request.id
    seeded_db.commit()

    approve_result = approval_engine.approve(
        approval_id=approval.id, resolved_by="alice", db=seeded_db
    )

    assert approve_result.status == "INVALID_STATE"
    payment = seeded_db.query(Payment).filter_by(payment_id="PAY-9003").one()
    assert payment.status.value == "SUCCEEDED"


def test_terminal_execution_cannot_be_resumed_incorrectly(seeded_db):
    result, execution = _request_refund_approval(seeded_db)
    execution_row = seeded_db.get(Execution, execution.id)
    execution_row.status = ExecutionStatus.COMPLETED
    seeded_db.commit()

    approve_result = approval_engine.approve(
        approval_id=uuid.UUID(result.approval_request_id), resolved_by="alice", db=seeded_db
    )

    assert approve_result.status == "INVALID_STATE"
    payment = seeded_db.query(Payment).filter_by(payment_id="PAY-9003").one()
    assert payment.status.value == "SUCCEEDED"


def test_approval_audit_events_ordered_correctly(seeded_db):
    result, execution = _request_refund_approval(seeded_db)
    approval_engine.approve(
        approval_id=uuid.UUID(result.approval_request_id), resolved_by="alice", db=seeded_db
    )

    event_types = [e.event_type.value for e in _events(seeded_db, execution.id)]
    assert event_types == [
        "TOOL_REQUESTED",
        "PERMISSION_CHECKED",
        "POLICY_EVALUATION_STARTED",
        "POLICY_MATCHED",
        "POLICY_APPROVAL_REQUIRED",
        "APPROVAL_REQUESTED",
        "APPROVAL_APPROVED",
        "APPROVED_ACTION_EXECUTION_STARTED",
        "APPROVED_ACTION_EXECUTED",
    ]
    assert [e.sequence for e in _events(seeded_db, execution.id)] == list(
        range(1, len(event_types) + 1)
    )


def test_rejection_audit_events_ordered_correctly(seeded_db):
    result, execution = _request_refund_approval(seeded_db)
    approval_engine.reject(
        approval_id=uuid.UUID(result.approval_request_id),
        resolved_by="bob",
        reason=None,
        db=seeded_db,
    )

    event_types = [e.event_type.value for e in _events(seeded_db, execution.id)]
    assert event_types == [
        "TOOL_REQUESTED",
        "PERMISSION_CHECKED",
        "POLICY_EVALUATION_STARTED",
        "POLICY_MATCHED",
        "POLICY_APPROVAL_REQUIRED",
        "APPROVAL_REQUESTED",
        "APPROVAL_REJECTED",
    ]


def test_tool_failure_after_approval_is_recorded_correctly(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    execution = _make_execution(seeded_db, agent)
    result = gateway.execute(
        agent_id=agent.id,
        execution_id=execution.id,
        tool_name="refund_payment",
        arguments={
            "payment_id": "PAY-9002",  # already refunded in seed data
            "amount": "750.00",
            "reason": "Duplicate transaction",
            "idempotency_key": f"gw-{uuid.uuid4()}",
        },
        db=seeded_db,
    )
    assert result.status == "REQUIRES_APPROVAL"  # $750 still routes through approval

    # Payment PAY-9002 is already REFUNDED per seed data, so approving this
    # request should hit ALREADY_REFUNDED inside the tool itself.
    payment = seeded_db.query(Payment).filter_by(payment_id="PAY-9002").one()
    payment.status = PaymentStatus.REFUNDED
    seeded_db.commit()

    approve_result = approval_engine.approve(
        approval_id=uuid.UUID(result.approval_request_id), resolved_by="alice", db=seeded_db
    )

    assert approve_result.status == "FAILED"
    tool_request = seeded_db.query(ToolRequest).filter_by(execution_id=execution.id).one()
    assert tool_request.status.value == "FAILED"
    assert tool_request.error["code"] == "ALREADY_REFUNDED"

    approval = seeded_db.get(ApprovalRequest, uuid.UUID(result.approval_request_id))
    assert approval.status.value == "EXECUTED"  # attempt was made, consumed exactly once


def test_unexpected_tool_exception_after_approval_does_not_leak(seeded_db, monkeypatch):
    result, execution = _request_refund_approval(seeded_db)

    from app.services import approval_engine as approval_engine_module

    registered_tool = approval_engine_module.tool_registry.get("refund_payment")
    secret = "sensitive internal stack trace"

    def explode(_args, _db):
        raise RuntimeError(secret)

    monkeypatch.setattr(registered_tool, "execute", explode)

    approve_result = approval_engine.approve(
        approval_id=uuid.UUID(result.approval_request_id), resolved_by="alice", db=seeded_db
    )

    assert approve_result.status == "FAILED"
    assert secret not in (approve_result.reason or "")
    tool_request = seeded_db.query(ToolRequest).filter_by(execution_id=execution.id).one()
    assert secret not in tool_request.error["message"]
    assert tool_request.error["code"] == "TOOL_EXECUTION_ERROR"


def test_deploy_production_approval_executes_deployment(seeded_db):
    agent = _agent(seeded_db, "devops-agent")
    execution = _make_execution(seeded_db, agent)
    service = seeded_db.query(Service).filter_by(name="checkout-service").one()

    result = gateway.execute(
        agent_id=agent.id,
        execution_id=execution.id,
        tool_name="deploy_production",
        arguments={"service_name": "checkout-service", "version": "approval-demo-1"},
        db=seeded_db,
    )
    assert result.status == "REQUIRES_APPROVAL"

    approve_result = approval_engine.approve(
        approval_id=uuid.UUID(result.approval_request_id), resolved_by="ops-lead", db=seeded_db
    )

    assert approve_result.status == "EXECUTED"
    versions = {
        d.version for d in seeded_db.query(Deployment).filter_by(service_id=service.id)
    }
    assert "approval-demo-1" in versions
