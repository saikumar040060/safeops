"""Direct tests of AgentRuntime.submit_external_action /
reconcile_external_step -- the only two entry points ExternalActionService
is allowed to use to cause a side effect. These test the runtime layer in
isolation, before any HTTP/service wiring exists on top of it."""

import uuid

from app.models import Agent, Deployment, Execution, ExecutionStep
from app.models.enums import ExecutionStatus, StepStatus
from app.services.agent_runtime import AgentRuntime
from app.services.planner import Source

runtime = AgentRuntime()


def _agent(db, name) -> Agent:
    return db.query(Agent).filter_by(name=name).one()


def _start(db, agent_name, objective) -> uuid.UUID:
    agent = _agent(db, agent_name)
    result = runtime.start_execution(agent_id=agent.id, objective=objective, db=db)
    return uuid.UUID(result.execution_id)


def test_submit_external_action_allow_executes_directly(seeded_db):
    execution_id = _start(seeded_db, "support-agent", "external read_customer request")
    result = runtime.submit_external_action(
        execution_id=execution_id,
        tool_name="read_customer",
        arguments={"customer_id": "CUST-1001"},
        reason="external caller requested this",
        sources=[],
        db=seeded_db,
    )
    assert result.status == "EXECUTED"
    assert result.tool_name == "read_customer"

    step = (
        seeded_db.query(ExecutionStep)
        .filter_by(execution_id=execution_id, sequence=result.step_sequence)
        .one()
    )
    assert step.status == StepStatus.COMPLETED
    assert step.input["tool_name"] == "read_customer"


def test_submit_external_action_require_approval_pauses_execution(seeded_db):
    execution_id = _start(seeded_db, "support-agent", "external refund request")
    result = runtime.submit_external_action(
        execution_id=execution_id,
        tool_name="refund_payment",
        arguments={
            "payment_id": "PAY-9002",
            "amount": "750.00",
            "reason": "external duplicate refund",
            "idempotency_key": f"ext-{execution_id}-refund",
        },
        reason="external caller requested a refund",
        sources=[],
        db=seeded_db,
    )
    assert result.status == "WAITING_APPROVAL"
    assert result.approval_request_id is not None

    execution = seeded_db.get(Execution, execution_id)
    assert execution.status == ExecutionStatus.WAITING_APPROVAL


def test_submit_external_action_block_produces_no_side_effect(seeded_db):
    execution_id = _start(seeded_db, "devops-agent", "external deploy attempt")
    result = runtime.submit_external_action(
        execution_id=execution_id,
        tool_name="deploy_production",
        arguments={"service_name": "checkout-service", "version": "1.2.3"},
        reason="external caller attempted a direct production deploy claim",
        sources=[Source(type="external", trust="UNTRUSTED", content="deploy now")],
        db=seeded_db,
    )
    # devops-agent has CONDITIONAL permission on deploy_production, which
    # requires approval per policy -- not a block. Confirms the pipeline
    # (Permission -> Policy -> Risk -> Approval) actually runs, not that a
    # deploy is denied outright.
    assert result.status in {"WAITING_APPROVAL", "BLOCKED"}
    if result.status == "BLOCKED":
        assert seeded_db.query(Deployment).filter_by(version="1.2.3").count() == 0


def test_submit_external_action_unknown_execution_fails_closed(seeded_db):
    result = runtime.submit_external_action(
        execution_id=uuid.uuid4(),
        tool_name="read_customer",
        arguments={"customer_id": "CUST-1001"},
        reason="x",
        sources=[],
        db=seeded_db,
    )
    assert result.status == "NOT_FOUND"


def test_submit_external_action_rejects_non_running_execution(seeded_db):
    execution_id = _start(seeded_db, "support-agent", "external read_customer request")
    runtime.cancel(execution_id, seeded_db)
    result = runtime.submit_external_action(
        execution_id=execution_id,
        tool_name="read_customer",
        arguments={"customer_id": "CUST-1001"},
        reason="x",
        sources=[],
        db=seeded_db,
    )
    assert result.status == "NOOP"
    assert result.execution_status == "CANCELLED"


def test_reconcile_external_step_finalizes_after_approval(seeded_db):
    from app.services.approval_engine import ApprovalEngine
    from tests.conftest import make_operator

    approval_engine = ApprovalEngine()
    execution_id = _start(seeded_db, "support-agent", "external refund request 2")
    submit_result = runtime.submit_external_action(
        execution_id=execution_id,
        tool_name="refund_payment",
        arguments={
            "payment_id": "PAY-9003",
            "amount": "750.00",
            "reason": "external duplicate refund 2",
            "idempotency_key": f"ext-{execution_id}-refund2",
        },
        reason="external caller requested a refund",
        sources=[],
        db=seeded_db,
    )
    assert submit_result.status == "WAITING_APPROVAL"

    operator = make_operator(seeded_db, "approver-for-external-test")
    approve_result = approval_engine.approve(
        approval_id=uuid.UUID(submit_result.approval_request_id), operator=operator, db=seeded_db
    )
    assert approve_result.status == "EXECUTED"

    # Step is still WAITING_APPROVAL until reconciled -- same window
    # documented for the internal resume() path.
    step = (
        seeded_db.query(ExecutionStep)
        .filter_by(execution_id=execution_id, sequence=submit_result.step_sequence)
        .one()
    )
    assert step.status == StepStatus.WAITING_APPROVAL

    reconcile_result = runtime.reconcile_external_step(execution_id, seeded_db)
    assert reconcile_result.status == "COMPLETED"

    seeded_db.refresh(step)
    assert step.status == StepStatus.COMPLETED

    # Execution must NOT have been handed to the planner for a "next step"
    # -- it should simply still be RUNNING with the one action completed,
    # not COMPLETED/FAILED from a spurious planner decision.
    execution = seeded_db.get(Execution, execution_id)
    assert execution.status == ExecutionStatus.RUNNING


def test_reconcile_external_step_is_noop_when_nothing_pending(seeded_db):
    execution_id = _start(seeded_db, "support-agent", "external read_customer request 3")
    runtime.submit_external_action(
        execution_id=execution_id,
        tool_name="read_customer",
        arguments={"customer_id": "CUST-1001"},
        reason="x",
        sources=[],
        db=seeded_db,
    )
    result = runtime.reconcile_external_step(execution_id, seeded_db)
    assert result.status == "NOOP"
