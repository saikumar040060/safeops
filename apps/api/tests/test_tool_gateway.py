import uuid

from app.models import (
    Agent,
    AgentToolPermission,
    AuditEvent,
    Deployment,
    Payment,
    Policy,
    PolicyDecision,
    Refund,
    Service,
    Tool,
    ToolRequest,
)
from app.models.enums import ExecutionStatus, PermissionType, PolicyAction
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


def test_refund_50_allowed_and_executed(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    execution = _make_execution(seeded_db, agent)

    result = gateway.execute(
        agent_id=agent.id,
        execution_id=execution.id,
        tool_name="refund_payment",
        arguments={
            "payment_id": "PAY-9002",
            "amount": "50.00",
            "reason": "goodwill",
            "idempotency_key": "gw-allow-50",
        },
        db=seeded_db,
    )

    assert result.status == "EXECUTED"
    assert result.decision == "ALLOW"
    assert result.matched_policy == "SUPPORT_REFUND_AUTONOMOUS"

    payment = seeded_db.query(Payment).filter_by(payment_id="PAY-9002").one()
    assert payment.status.value == "REFUNDED"
    assert seeded_db.query(Refund).filter_by(payment_id=payment.id).count() == 1

    request = seeded_db.query(ToolRequest).filter_by(execution_id=execution.id).one()
    assert request.status.value == "EXECUTED"

    decision = seeded_db.query(PolicyDecision).filter_by(execution_id=execution.id).one()
    assert decision.decision.value == "ALLOW"
    assert decision.matched_policy_key == "SUPPORT_REFUND_AUTONOMOUS"
    assert decision.tool_request_id == request.id

    event_types = [e.event_type.value for e in _events(seeded_db, execution.id)]
    assert event_types == [
        "TOOL_REQUESTED",
        "PERMISSION_CHECKED",
        "POLICY_EVALUATION_STARTED",
        "POLICY_MATCHED",
        "POLICY_ALLOWED",
        "RISK_ASSESSMENT_STARTED",
        "RISK_SIGNAL_DETECTED",
        "RISK_ASSESSED",
        "ACTION_ALLOWED",
        "TOOL_EXECUTED",
    ]


def test_refund_100_boundary_allowed(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    execution = _make_execution(seeded_db, agent)

    result = gateway.execute(
        agent_id=agent.id,
        execution_id=execution.id,
        tool_name="refund_payment",
        arguments={
            "payment_id": "PAY-9003",
            "amount": "100.00",
            "reason": "goodwill",
            "idempotency_key": "gw-allow-100",
        },
        db=seeded_db,
    )

    assert result.status == "EXECUTED"
    assert result.decision == "ALLOW"
    assert result.matched_policy == "SUPPORT_REFUND_AUTONOMOUS"

    payment = seeded_db.query(Payment).filter_by(payment_id="PAY-9003").one()
    assert payment.status.value == "REFUNDED"


def test_refund_100_01_requires_approval_and_does_not_execute(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    execution = _make_execution(seeded_db, agent)

    result = gateway.execute(
        agent_id=agent.id,
        execution_id=execution.id,
        tool_name="refund_payment",
        arguments={
            "payment_id": "PAY-9003",
            "amount": "100.01",
            "reason": "duplicate",
            "idempotency_key": "gw-approval-100.01",
        },
        db=seeded_db,
    )

    assert result.status == "REQUIRES_APPROVAL"
    assert result.decision == "REQUIRE_APPROVAL"
    assert result.matched_policy == "SUPPORT_REFUND_APPROVAL"

    payment = seeded_db.query(Payment).filter_by(payment_id="PAY-9003").one()
    assert payment.status.value == "SUCCEEDED"  # untouched: tool never ran
    assert seeded_db.query(Refund).count() == 0

    request = seeded_db.query(ToolRequest).filter_by(execution_id=execution.id).one()
    assert request.status.value == "REQUIRES_APPROVAL"

    decision = seeded_db.query(PolicyDecision).filter_by(execution_id=execution.id).one()
    assert decision.decision.value == "REQUIRE_APPROVAL"
    assert decision.matched_policy_key == "SUPPORT_REFUND_APPROVAL"

    event_types = [e.event_type.value for e in _events(seeded_db, execution.id)]
    assert event_types == [
        "TOOL_REQUESTED",
        "PERMISSION_CHECKED",
        "POLICY_EVALUATION_STARTED",
        "POLICY_MATCHED",
        "POLICY_APPROVAL_REQUIRED",
        "RISK_ASSESSMENT_STARTED",
        "RISK_SIGNAL_DETECTED",
        "RISK_ASSESSED",
        "APPROVAL_REQUESTED",
    ]


def test_refund_750_requires_approval_and_does_not_execute(seeded_db):
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
            "idempotency_key": "gw-approval-750",
        },
        db=seeded_db,
    )

    assert result.status == "REQUIRES_APPROVAL"
    assert result.decision == "REQUIRE_APPROVAL"

    payment = seeded_db.query(Payment).filter_by(payment_id="PAY-9003").one()
    assert payment.status.value == "SUCCEEDED"  # untouched: tool never ran
    assert seeded_db.query(Refund).count() == 0


def test_refund_1000_boundary_requires_approval(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    execution = _make_execution(seeded_db, agent)

    result = gateway.execute(
        agent_id=agent.id,
        execution_id=execution.id,
        tool_name="refund_payment",
        arguments={
            "payment_id": "PAY-9003",
            "amount": "1000.00",
            "reason": "duplicate",
            "idempotency_key": "gw-approval-1000",
        },
        db=seeded_db,
    )

    assert result.status == "REQUIRES_APPROVAL"
    assert result.decision == "REQUIRE_APPROVAL"
    assert result.matched_policy == "SUPPORT_REFUND_APPROVAL"


def test_refund_1000_01_blocked_and_does_not_execute(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    execution = _make_execution(seeded_db, agent)

    result = gateway.execute(
        agent_id=agent.id,
        execution_id=execution.id,
        tool_name="refund_payment",
        arguments={
            "payment_id": "PAY-9003",
            "amount": "1000.01",
            "reason": "duplicate",
            "idempotency_key": "gw-block-1000.01",
        },
        db=seeded_db,
    )

    assert result.status == "BLOCKED"
    assert result.decision == "BLOCK"
    assert result.matched_policy == "SUPPORT_REFUND_BLOCK"

    payment = seeded_db.query(Payment).filter_by(payment_id="PAY-9003").one()
    assert payment.status.value == "SUCCEEDED"
    assert seeded_db.query(Refund).count() == 0

    request = seeded_db.query(ToolRequest).filter_by(execution_id=execution.id).one()
    assert request.status.value == "DENIED"

    decision = seeded_db.query(PolicyDecision).filter_by(execution_id=execution.id).one()
    assert decision.decision.value == "BLOCK"
    assert decision.matched_policy_key == "SUPPORT_REFUND_BLOCK"

    event_types = [e.event_type.value for e in _events(seeded_db, execution.id)]
    assert event_types == [
        "TOOL_REQUESTED",
        "PERMISSION_CHECKED",
        "POLICY_EVALUATION_STARTED",
        "POLICY_MATCHED",
        "POLICY_BLOCKED",
    ]


def test_refund_10000_blocked_and_does_not_execute(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    execution = _make_execution(seeded_db, agent)

    result = gateway.execute(
        agent_id=agent.id,
        execution_id=execution.id,
        tool_name="refund_payment",
        arguments={
            "payment_id": "PAY-9003",
            "amount": "10000.00",
            "reason": "duplicate",
            "idempotency_key": "gw-block-10000",
        },
        db=seeded_db,
    )

    assert result.status == "BLOCKED"
    assert result.decision == "BLOCK"

    payment = seeded_db.query(Payment).filter_by(payment_id="PAY-9003").one()
    assert payment.status.value == "SUCCEEDED"
    assert seeded_db.query(Refund).count() == 0


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


def test_devops_agent_deploy_staging_conditional_allowed_and_executed(seeded_db):
    agent = _agent(seeded_db, "devops-agent")
    execution = _make_execution(seeded_db, agent)
    service = seeded_db.query(Service).filter_by(name="checkout-service").one()

    result = gateway.execute(
        agent_id=agent.id,
        execution_id=execution.id,
        tool_name="deploy_staging",
        arguments={"service_name": "checkout-service", "version": "9.9.9-staging"},
        db=seeded_db,
    )

    assert result.status == "EXECUTED"
    assert result.decision == "ALLOW"
    assert result.matched_policy == "DEVOPS_STAGING_DEPLOY"

    versions = {d.version for d in seeded_db.query(Deployment).filter_by(service_id=service.id)}
    assert "9.9.9-staging" in versions

    request = seeded_db.query(ToolRequest).filter_by(execution_id=execution.id).one()
    assert request.status.value == "EXECUTED"

    event_types = [e.event_type.value for e in _events(seeded_db, execution.id)]
    assert event_types == [
        "TOOL_REQUESTED",
        "PERMISSION_CHECKED",
        "POLICY_EVALUATION_STARTED",
        "POLICY_MATCHED",
        "POLICY_ALLOWED",
        "RISK_ASSESSMENT_STARTED",
        "RISK_ASSESSED",
        "ACTION_ALLOWED",
        "TOOL_EXECUTED",
    ]


def test_devops_agent_deploy_production_requires_approval_and_does_not_execute(seeded_db):
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

    assert result.status == "REQUIRES_APPROVAL"
    assert result.decision == "REQUIRE_APPROVAL"
    assert result.matched_policy == "DEVOPS_PRODUCTION_DEPLOY"

    versions = {d.version for d in seeded_db.query(Deployment).filter_by(service_id=service.id)}
    assert "9.9.9-conditional" not in versions

    request = seeded_db.query(ToolRequest).filter_by(execution_id=execution.id).one()
    assert request.status.value == "REQUIRES_APPROVAL"

    decision = seeded_db.query(PolicyDecision).filter_by(execution_id=execution.id).one()
    assert decision.decision.value == "REQUIRE_APPROVAL"
    assert decision.matched_policy_key == "DEVOPS_PRODUCTION_DEPLOY"

    event_types = [e.event_type.value for e in _events(seeded_db, execution.id)]
    assert event_types == [
        "TOOL_REQUESTED",
        "PERMISSION_CHECKED",
        "POLICY_EVALUATION_STARTED",
        "POLICY_MATCHED",
        "POLICY_APPROVAL_REQUIRED",
        "RISK_ASSESSMENT_STARTED",
        "RISK_ASSESSED",
        "APPROVAL_REQUESTED",
    ]


def test_conditional_with_no_matching_policy_fails_closed(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    execution = _make_execution(seeded_db, agent)

    # get_payments is normally ALLOW; flip it to CONDITIONAL with no policy
    # configured for this agent/tool to exercise the fail-closed path.
    tool = seeded_db.query(Tool).filter_by(name="get_payments").one()
    permission = (
        seeded_db.query(AgentToolPermission).filter_by(agent_id=agent.id, tool_id=tool.id).one()
    )
    permission.permission = PermissionType.CONDITIONAL
    seeded_db.commit()

    result = gateway.execute(
        agent_id=agent.id,
        execution_id=execution.id,
        tool_name="get_payments",
        arguments={"customer_id": "CUST-1001"},
        db=seeded_db,
    )

    assert result.status == "BLOCKED"
    assert result.decision == "BLOCK"
    assert result.matched_policy is None
    assert "NO_MATCHING_POLICY" in result.reason

    request = seeded_db.query(ToolRequest).filter_by(execution_id=execution.id).one()
    assert request.status.value == "DENIED"

    decision = seeded_db.query(PolicyDecision).filter_by(execution_id=execution.id).one()
    assert decision.decision.value == "BLOCK"
    assert decision.matched_policy_key is None

    event_types = [e.event_type.value for e in _events(seeded_db, execution.id)]
    assert event_types == [
        "TOOL_REQUESTED",
        "PERMISSION_CHECKED",
        "POLICY_EVALUATION_STARTED",
        "POLICY_BLOCKED",
    ]


def test_malformed_policy_reason_does_not_leak_condition_data(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    execution = _make_execution(seeded_db, agent)
    tool = seeded_db.query(Tool).filter_by(name="refund_payment").one()
    secret = "do-not-persist-this-policy-secret"
    seeded_db.add(
        Policy(
            policy_key="TEST_MALFORMED_SECRET",
            name="malformed",
            agent_type="support",
            tool_id=tool.id,
            priority=999,
            enabled=True,
            action=PolicyAction.ALLOW,
            conditions={"all": [{"field": secret}]},
        )
    )
    seeded_db.commit()

    result = gateway.execute(
        agent_id=agent.id,
        execution_id=execution.id,
        tool_name="refund_payment",
        arguments={
            "payment_id": "PAY-9003",
            "amount": "50.00",
            "reason": "goodwill",
            "idempotency_key": "gw-malformed-secret",
        },
        db=seeded_db,
    )

    request = seeded_db.query(ToolRequest).filter_by(execution_id=execution.id).one()
    decision = seeded_db.query(PolicyDecision).filter_by(execution_id=execution.id).one()
    assert result.status == "BLOCKED"
    assert secret not in (result.reason or "")
    assert secret not in request.error["message"]
    assert secret not in decision.reason


def test_unexpected_policy_exception_fails_closed_without_leaking(seeded_db, monkeypatch):
    agent = _agent(seeded_db, "devops-agent")
    execution = _make_execution(seeded_db, agent)
    secret = "sensitive evaluator internals"

    def explode(**_kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr("app.services.tool_gateway.policy_engine.evaluate", explode)
    result = gateway.execute(
        agent_id=agent.id,
        execution_id=execution.id,
        tool_name="deploy_staging",
        arguments={"service_name": "checkout-service", "version": "never-deployed"},
        db=seeded_db,
    )

    request = seeded_db.query(ToolRequest).filter_by(execution_id=execution.id).one()
    decision = seeded_db.query(PolicyDecision).filter_by(execution_id=execution.id).one()
    assert result.status == "BLOCKED"
    assert result.matched_policy is None
    assert request.status.value == "DENIED"
    assert decision.decision.value == "BLOCK"
    assert decision.matched_policy_id is None
    assert secret not in (result.reason or "")
    assert secret not in request.error["message"]
    assert secret not in decision.reason
    assert [e.event_type.value for e in _events(seeded_db, execution.id)] == [
        "TOOL_REQUESTED",
        "PERMISSION_CHECKED",
        "POLICY_EVALUATION_STARTED",
        "POLICY_BLOCKED",
    ]


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
    versions = {d.version for d in seeded_db.query(Deployment).filter_by(service_id=service.id)}
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
        "RISK_ASSESSMENT_STARTED",
        "RISK_ASSESSED",
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


def test_cancelled_execution_cannot_call_tools(seeded_db):
    # Regression: NON_EXECUTABLE_STATUSES must include CANCELLED (a
    # milestone 8 status) or a cancellation racing an in-flight
    # AgentRuntime step can let the tool execute anyway -- see
    # test_agent_runtime.py's cancellation-race regression tests.
    agent = _agent(seeded_db, "support-agent")
    execution = _make_execution(seeded_db, agent, status=ExecutionStatus.CANCELLED)

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
        "RISK_ASSESSMENT_STARTED",
        "RISK_ASSESSED",
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
    assert len(events) == 12  # 6 events per successful direct-ALLOW call
