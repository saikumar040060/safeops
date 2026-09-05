import uuid

from app.models import Agent, AuditEvent, Deployment, Payment, Service, ToolRequest
from app.models.enums import ExecutionStatus
from app.services.tool_gateway import ToolGateway

gateway = ToolGateway()


def _agent(db, name) -> Agent:
    return db.query(Agent).filter_by(name=name).one()


def _make_execution(db, agent, status=ExecutionStatus.RUNNING, objective="test objective"):
    from app.models import Execution

    execution = Execution(agent_id=agent.id, objective=objective, status=status)
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


def test_support_agent_read_customer_allowed(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    execution = _make_execution(seeded_db, agent)

    result = gateway.execute(
        agent_id=agent.id,
        execution_id=execution.id,
        tool_name="read_customer",
        arguments={"customer_id": "CUST-1001"},
        db=seeded_db,
    )

    assert result.status == "EXECUTED"
    assert result.decision == "ALLOW"
    assert result.tool_result["customer_id"] == "CUST-1001"


def test_support_agent_read_logs_denied(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    execution = _make_execution(seeded_db, agent)

    result = gateway.execute(
        agent_id=agent.id,
        execution_id=execution.id,
        tool_name="read_logs",
        arguments={"service_name": "checkout-service"},
        db=seeded_db,
    )

    assert result.status == "BLOCKED"
    assert result.decision == "DENY"


def test_support_agent_refund_payment_needs_policy_evaluation(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    execution = _make_execution(seeded_db, agent)

    result = gateway.execute(
        agent_id=agent.id,
        execution_id=execution.id,
        tool_name="refund_payment",
        arguments={
            "payment_id": "PAY-9003",
            "amount": "750.00",
            "reason": "duplicate",
            "idempotency_key": "gw-conditional-1",
        },
        db=seeded_db,
    )

    assert result.status == "NEEDS_POLICY_EVALUATION"
    assert result.decision == "CONDITIONAL"

    payment = seeded_db.query(Payment).filter_by(payment_id="PAY-9003").one()
    assert payment.status.value == "SUCCEEDED"  # untouched: tool never ran


def test_devops_agent_read_logs_allowed(seeded_db):
    agent = _agent(seeded_db, "devops-agent")
    execution = _make_execution(seeded_db, agent)

    result = gateway.execute(
        agent_id=agent.id,
        execution_id=execution.id,
        tool_name="read_logs",
        arguments={"service_name": "checkout-service", "limit": 2},
        db=seeded_db,
    )

    assert result.status == "EXECUTED"
    assert result.decision == "ALLOW"


def test_devops_agent_customer_tool_denied(seeded_db):
    agent = _agent(seeded_db, "devops-agent")
    execution = _make_execution(seeded_db, agent)

    result = gateway.execute(
        agent_id=agent.id,
        execution_id=execution.id,
        tool_name="read_customer",
        arguments={"customer_id": "CUST-1001"},
        db=seeded_db,
    )

    assert result.status == "BLOCKED"
    assert result.decision == "DENY"


def test_devops_agent_deploy_production_needs_policy_evaluation(seeded_db):
    agent = _agent(seeded_db, "devops-agent")
    execution = _make_execution(seeded_db, agent)
    service = seeded_db.query(Service).filter_by(name="checkout-service").one()

    result = gateway.execute(
        agent_id=agent.id,
        execution_id=execution.id,
        tool_name="deploy_production",
        arguments={"service_name": "checkout-service", "version": "9.9.9-conditional"},
        db=seeded_db,
    )

    assert result.status == "NEEDS_POLICY_EVALUATION"
    assert result.decision == "CONDITIONAL"

    versions = {
        d.version for d in seeded_db.query(Deployment).filter_by(service_id=service.id)
    }
    assert "9.9.9-conditional" not in versions

    event_types = [e.event_type.value for e in _events(seeded_db, execution.id)]
    assert event_types == ["TOOL_REQUESTED", "PERMISSION_CHECKED", "POLICY_EVALUATION_REQUIRED"]


def test_no_tool_execution_when_denied(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    execution = _make_execution(seeded_db, agent)
    service = seeded_db.query(Service).filter_by(name="checkout-service").one()

    result = gateway.execute(
        agent_id=agent.id,
        execution_id=execution.id,
        tool_name="deploy_production",
        arguments={"service_name": "checkout-service", "version": "9.9.9-denied"},
        db=seeded_db,
    )

    assert result.status == "BLOCKED"
    versions = {
        d.version for d in seeded_db.query(Deployment).filter_by(service_id=service.id)
    }
    assert "9.9.9-denied" not in versions

    event_types = [e.event_type.value for e in _events(seeded_db, execution.id)]
    assert event_types == ["TOOL_REQUESTED", "PERMISSION_CHECKED", "ACTION_DENIED"]


def test_unknown_tool(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    execution = _make_execution(seeded_db, agent)

    result = gateway.execute(
        agent_id=agent.id,
        execution_id=execution.id,
        tool_name="does_not_exist",
        arguments={},
        db=seeded_db,
    )

    assert result.status == "FAILED"
    request = seeded_db.query(ToolRequest).filter_by(execution_id=execution.id).one()
    assert request.status.value == "FAILED"
    assert request.tool_id is None


def test_missing_agent(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    execution = _make_execution(seeded_db, agent)

    result = gateway.execute(
        agent_id=uuid.uuid4(),
        execution_id=execution.id,
        tool_name="read_customer",
        arguments={"customer_id": "CUST-1001"},
        db=seeded_db,
    )

    assert result.status == "FAILED"
    assert seeded_db.query(ToolRequest).count() == 0
    assert len(_events(seeded_db, execution.id)) == 0


def test_registry_tool_missing_database_row_defaults_to_deny(seeded_db, monkeypatch):
    agent = _agent(seeded_db, "support-agent")
    execution = _make_execution(seeded_db, agent)

    from app.services import tool_gateway

    registered_tool = tool_gateway.tool_registry.get("read_customer")
    monkeypatch.setattr(tool_gateway.tool_registry, "get", lambda _name: registered_tool)

    result = gateway.execute(
        agent_id=agent.id,
        execution_id=execution.id,
        tool_name="registered_but_not_seeded",
        arguments={"customer_id": "CUST-1001"},
        db=seeded_db,
    )

    assert result.status == "BLOCKED"
    assert result.decision == "DENY"
    request = seeded_db.query(ToolRequest).filter_by(execution_id=execution.id).one()
    assert request.status.value == "DENIED"
    assert request.tool_id is None
    assert [event.event_type.value for event in _events(seeded_db, execution.id)] == [
        "TOOL_REQUESTED",
        "PERMISSION_CHECKED",
        "ACTION_DENIED",
    ]


def test_unexpected_tool_exception_is_persisted_as_failure(seeded_db, monkeypatch):
    agent = _agent(seeded_db, "support-agent")
    execution = _make_execution(seeded_db, agent)

    from app.services import tool_gateway

    registered_tool = tool_gateway.tool_registry.get("read_customer")

    def raise_unexpected(_arguments, db):
        db.rollback()
        raise RuntimeError("sensitive internal detail")

    monkeypatch.setattr(registered_tool, "execute", raise_unexpected)

    result = gateway.execute(
        agent_id=agent.id,
        execution_id=execution.id,
        tool_name="read_customer",
        arguments={"customer_id": "CUST-1001"},
        db=seeded_db,
    )

    assert result.status == "FAILED"
    assert result.reason == "Tool execution raised an unexpected error"
    request = seeded_db.query(ToolRequest).filter_by(execution_id=execution.id).one()
    assert request.status.value == "FAILED"
    assert request.error["code"] == "TOOL_EXECUTION_ERROR"
    assert "sensitive internal detail" not in str(request.error)
    assert [event.event_type.value for event in _events(seeded_db, execution.id)] == [
        "TOOL_REQUESTED",
        "PERMISSION_CHECKED",
        "ACTION_ALLOWED",
        "TOOL_FAILED",
    ]


def test_missing_execution(seeded_db):
    agent = _agent(seeded_db, "support-agent")

    result = gateway.execute(
        agent_id=agent.id,
        execution_id=uuid.uuid4(),
        tool_name="read_customer",
        arguments={"customer_id": "CUST-1001"},
        db=seeded_db,
    )

    assert result.status == "FAILED"
    assert seeded_db.query(ToolRequest).count() == 0


def test_execution_agent_mismatch(seeded_db):
    support = _agent(seeded_db, "support-agent")
    devops = _agent(seeded_db, "devops-agent")
    execution = _make_execution(seeded_db, support)

    result = gateway.execute(
        agent_id=devops.id,
        execution_id=execution.id,
        tool_name="read_logs",
        arguments={"service_name": "checkout-service"},
        db=seeded_db,
    )

    assert result.status == "FAILED"
    assert seeded_db.query(ToolRequest).count() == 0
    assert len(_events(seeded_db, execution.id)) == 0


def test_completed_execution_cannot_call_tools(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    execution = _make_execution(seeded_db, agent, status=ExecutionStatus.COMPLETED)

    result = gateway.execute(
        agent_id=agent.id,
        execution_id=execution.id,
        tool_name="read_customer",
        arguments={"customer_id": "CUST-1001"},
        db=seeded_db,
    )

    assert result.status == "FAILED"
    assert seeded_db.query(ToolRequest).count() == 0


def test_invalid_tool_arguments(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    execution = _make_execution(seeded_db, agent)

    result = gateway.execute(
        agent_id=agent.id,
        execution_id=execution.id,
        tool_name="read_customer",
        arguments={},
        db=seeded_db,
    )

    assert result.status == "FAILED"
    request = seeded_db.query(ToolRequest).filter_by(execution_id=execution.id).one()
    assert request.status.value == "FAILED"
    assert request.error["code"] == "INVALID_ARGUMENTS"

    # invalid arguments short-circuit before the permission check
    event_types = [e.event_type.value for e in _events(seeded_db, execution.id)]
    assert event_types == ["TOOL_REQUESTED", "TOOL_FAILED"]


def test_underlying_tool_domain_failure(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    execution = _make_execution(seeded_db, agent)

    result = gateway.execute(
        agent_id=agent.id,
        execution_id=execution.id,
        tool_name="read_customer",
        arguments={"customer_id": "CUST-9999"},
        db=seeded_db,
    )

    assert result.status == "FAILED"
    assert result.decision == "ALLOW"
    request = seeded_db.query(ToolRequest).filter_by(execution_id=execution.id).one()
    assert request.status.value == "FAILED"
    assert request.error["code"] == "NOT_FOUND"


def test_tool_request_persisted_on_success(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    execution = _make_execution(seeded_db, agent)

    gateway.execute(
        agent_id=agent.id,
        execution_id=execution.id,
        tool_name="read_customer",
        arguments={"customer_id": "CUST-1001"},
        db=seeded_db,
    )

    request = seeded_db.query(ToolRequest).filter_by(execution_id=execution.id).one()
    assert request.status.value == "EXECUTED"
    assert request.result["customer_id"] == "CUST-1001"
    assert request.completed_at is not None


def test_audit_events_emitted_in_correct_order_on_success(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    execution = _make_execution(seeded_db, agent)

    gateway.execute(
        agent_id=agent.id,
        execution_id=execution.id,
        tool_name="read_customer",
        arguments={"customer_id": "CUST-1001"},
        db=seeded_db,
    )

    events = _events(seeded_db, execution.id)
    assert [e.event_type.value for e in events] == [
        "TOOL_REQUESTED",
        "PERMISSION_CHECKED",
        "ACTION_ALLOWED",
        "TOOL_EXECUTED",
    ]
    assert [e.sequence for e in events] == list(range(1, len(events) + 1))


def test_multiple_calls_on_same_execution_get_sequential_audit_numbers(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    execution = _make_execution(seeded_db, agent)

    gateway.execute(
        agent_id=agent.id,
        execution_id=execution.id,
        tool_name="read_customer",
        arguments={"customer_id": "CUST-1001"},
        db=seeded_db,
    )
    gateway.execute(
        agent_id=agent.id,
        execution_id=execution.id,
        tool_name="get_payments",
        arguments={"customer_id": "CUST-1001"},
        db=seeded_db,
    )

    events = _events(seeded_db, execution.id)
    assert [e.sequence for e in events] == list(range(1, len(events) + 1))
    assert len(events) == 8  # 4 events per successful call
