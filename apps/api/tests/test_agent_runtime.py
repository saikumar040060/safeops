import inspect
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy.orm import Session

from app.models import (
    Agent,
    AuditEvent,
    Deployment,
    Execution,
    ExecutionStep,
    Payment,
    Refund,
    SecurityIncident,
    ToolRequest,
)
from app.models.enums import ExecutionStatus, StepStatus, ToolRequestStatus
from app.services import agent_runtime as agent_runtime_module
from app.services import planner as planner_module
from app.services.agent_runtime import AgentRuntime
from app.services.approval_engine import ApprovalEngine
from app.services.planner import ToolAction

runtime = AgentRuntime()
approval_engine = ApprovalEngine()


def _agent(db, name) -> Agent:
    return db.query(Agent).filter_by(name=name).one()


def _events(db, execution_id):
    return (
        db.query(AuditEvent)
        .filter_by(execution_id=execution_id)
        .order_by(AuditEvent.sequence)
        .all()
    )


def _steps(db, execution_id):
    return (
        db.query(ExecutionStep)
        .filter_by(execution_id=execution_id)
        .order_by(ExecutionStep.sequence)
        .all()
    )


class FakePlanner:
    """Test double letting individual tests dictate exactly what the
    "planner" proposes, independent of DeterministicPlanner's keyword
    matching."""

    def __init__(self, decisions):
        self._decisions = list(decisions)

    def next_action(self, execution, context, history):
        if callable(self._decisions[0]):
            return self._decisions.pop(0)(execution, context, history)
        return self._decisions.pop(0)


# ---------------------------------------------------------------------------
# No-bypass proof (static + behavioral)
# ---------------------------------------------------------------------------


def test_agent_runtime_source_never_calls_tools_directly():
    source = inspect.getsource(agent_runtime_module)
    import_lines = [
        line
        for line in source.splitlines()
        if line.strip().startswith(("import ", "from ")) and "typing" not in line
    ]
    assert not any("tool_registry" in line or "app.tools" in line for line in import_lines)
    # A bypass would look like `tool.execute(...)` / `.get(tool_name).execute(...)`
    # -- the only call that can cause a side effect is self.gateway.execute().
    assert "tool.execute(" not in source
    assert ".get(action" not in source
    assert "self.gateway.execute(" in source


def test_planner_module_has_no_tool_or_code_execution_imports():
    source = inspect.getsource(planner_module)
    for forbidden in ("tool_registry", "BaseTool", "eval(", "exec(", "subprocess", "os.system"):
        assert forbidden not in source


def test_agent_runtime_has_no_code_execution_primitives():
    source = inspect.getsource(agent_runtime_module)
    for forbidden in ("eval(", "exec(", "subprocess", "os.system", "__import__"):
        assert forbidden not in source


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


def test_start_execution_transitions_created_to_running(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    result = runtime.start_execution(
        agent_id=agent.id, objective="test objective", db=seeded_db
    )
    assert result.status == "CREATED"
    assert result.execution_status == "RUNNING"

    execution = seeded_db.get(Execution, uuid.UUID(result.execution_id))
    assert execution.status == ExecutionStatus.RUNNING
    events = [e.event_type.value for e in _events(seeded_db, execution.id)]
    assert events == ["EXECUTION_STARTED"]


def test_start_execution_unknown_agent_fails_closed(seeded_db):
    result = runtime.start_execution(
        agent_id=uuid.uuid4(), objective="test objective", db=seeded_db
    )
    assert result.status == "NOT_FOUND"


def test_terminal_execution_cannot_step(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    execution = Execution(agent_id=agent.id, objective="x", status=ExecutionStatus.COMPLETED)
    seeded_db.add(execution)
    seeded_db.commit()

    result = runtime.step(execution.id, seeded_db)
    assert result.status == "NOOP"
    assert _steps(seeded_db, execution.id) == []


def test_cancelled_execution_cannot_step(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    execution = Execution(agent_id=agent.id, objective="x", status=ExecutionStatus.CANCELLED)
    seeded_db.add(execution)
    seeded_db.commit()

    result = runtime.step(execution.id, seeded_db)
    assert result.status == "NOOP"


def test_no_planning_while_waiting_approval(seeded_db, monkeypatch):
    agent = _agent(seeded_db, "support-agent")
    execution = Execution(agent_id=agent.id, objective="x", status=ExecutionStatus.WAITING_APPROVAL)
    seeded_db.add(execution)
    seeded_db.commit()

    def explode(*_a, **_kw):
        raise AssertionError("planner must not be called while waiting for approval")

    fake_runtime = AgentRuntime(planner=type("P", (), {"next_action": explode})())
    result = fake_runtime.step(execution.id, seeded_db)
    assert result.status == "NOOP"

    resume_result = fake_runtime.resume(execution.id, seeded_db)
    assert resume_result.status == "NOOP"


# ---------------------------------------------------------------------------
# Malformed / hostile planner output
# ---------------------------------------------------------------------------


def test_malformed_planner_output_fails_closed(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    start = runtime.start_execution(agent_id=agent.id, objective="test objective", db=seeded_db)
    execution_id = uuid.UUID(start.execution_id)

    fake_runtime = AgentRuntime(planner=FakePlanner(["not-a-valid-decision"]))
    result = fake_runtime.step(execution_id, seeded_db)
    assert result.status == "FAILED"
    execution = seeded_db.get(Execution, execution_id)
    assert execution.status == ExecutionStatus.FAILED


def test_planner_exception_fails_closed_without_leaking(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    start = runtime.start_execution(agent_id=agent.id, objective="test objective", db=seeded_db)
    execution_id = uuid.UUID(start.execution_id)

    def explode(execution, context, history):
        raise RuntimeError("sensitive internal detail")

    fake_runtime = AgentRuntime(planner=FakePlanner([explode]))
    result = fake_runtime.step(execution_id, seeded_db)
    assert result.status == "FAILED"
    assert "sensitive internal detail" not in (result.reason or "")
    step = _steps(seeded_db, execution_id)[-1]
    assert "sensitive internal detail" not in str(step.output)


def test_unknown_tool_fails_closed(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    start = runtime.start_execution(agent_id=agent.id, objective="test objective", db=seeded_db)
    execution_id = uuid.UUID(start.execution_id)

    fake_runtime = AgentRuntime(
        planner=FakePlanner(
            [ToolAction(tool_name="does_not_exist", arguments={}, reason="probe")]
        )
    )
    result = fake_runtime.step(execution_id, seeded_db)
    assert result.status == "FAILED"
    execution = seeded_db.get(Execution, execution_id)
    assert execution.status == ExecutionStatus.FAILED
    # Unknown tool is not read-only-retryable: exactly one step, no loop.
    assert len(_steps(seeded_db, execution_id)) == 1


def test_invalid_arguments_fail_closed(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    start = runtime.start_execution(agent_id=agent.id, objective="test objective", db=seeded_db)
    execution_id = uuid.UUID(start.execution_id)

    fake_runtime = AgentRuntime(
        planner=FakePlanner(
            [ToolAction(tool_name="read_customer", arguments={}, reason="missing required arg")]
        )
    )
    result = fake_runtime.step(execution_id, seeded_db)
    # read_customer is read-only: one retry is allowed, then FAILED.
    assert result.status == "FAILED"
    execution = seeded_db.get(Execution, execution_id)
    assert execution.status == ExecutionStatus.FAILED


def test_read_only_tool_failure_retries_once_then_fails(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    start = runtime.start_execution(agent_id=agent.id, objective="test objective", db=seeded_db)
    execution_id = uuid.UUID(start.execution_id)

    fake_runtime = AgentRuntime(
        planner=FakePlanner(
            [
                ToolAction(
                    tool_name="read_customer",
                    arguments={"customer_id": "CUST-9999"},
                    reason="x",
                )
            ]
        )
    )
    result = fake_runtime.step(execution_id, seeded_db)
    assert result.status == "FAILED"
    steps = _steps(seeded_db, execution_id)
    assert len(steps) == 2  # original attempt + exactly one retry
    assert all(s.status == StepStatus.FAILED for s in steps)
    assert seeded_db.get(Execution, execution_id).status == ExecutionStatus.FAILED


def test_side_effecting_tool_failure_never_retries(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    start = runtime.start_execution(agent_id=agent.id, objective="test objective", db=seeded_db)
    execution_id = uuid.UUID(start.execution_id)

    fake_runtime = AgentRuntime(
        planner=FakePlanner(
            [
                ToolAction(
                    tool_name="refund_payment",
                    arguments={
                        "payment_id": "PAY-DOES-NOT-EXIST",
                        "amount": "1.00",
                        "reason": "x",
                        "idempotency_key": f"probe-{uuid.uuid4()}",
                    },
                    reason="x",
                )
            ]
        )
    )
    result = fake_runtime.step(execution_id, seeded_db)
    assert result.status == "FAILED"
    assert len(_steps(seeded_db, execution_id)) == 1


# ---------------------------------------------------------------------------
# Support workflow: read -> get_payments -> refund -> approval -> resume
# ---------------------------------------------------------------------------


def _run_refund_workflow_to_approval(db):
    agent = _agent(db, "support-agent")
    start = runtime.start_execution(
        agent_id=agent.id,
        objective="Investigate duplicate payment for CUST-1001 and refund the duplicate",
        db=db,
    )
    execution_id = uuid.UUID(start.execution_id)

    r1 = runtime.step(execution_id, db)
    assert r1.status == "EXECUTED" and r1.tool_name == "read_customer"
    r2 = runtime.step(execution_id, db)
    assert r2.status == "EXECUTED" and r2.tool_name == "get_payments"
    r3 = runtime.step(execution_id, db)
    assert r3.status == "WAITING_APPROVAL" and r3.tool_name == "refund_payment"
    return execution_id, r3


def test_support_workflow_tool_order(seeded_db):
    execution_id, _ = _run_refund_workflow_to_approval(seeded_db)
    steps = _steps(seeded_db, execution_id)
    assert [s.input["tool_name"] for s in steps] == [
        "read_customer",
        "get_payments",
        "refund_payment",
    ]
    assert [s.sequence for s in steps] == [1, 2, 3]


def test_approval_pauses_runtime(seeded_db):
    execution_id, result = _run_refund_workflow_to_approval(seeded_db)
    execution = seeded_db.get(Execution, execution_id)
    assert execution.status == ExecutionStatus.WAITING_APPROVAL
    assert result.approval_request_id is not None


def test_resume_after_approval_completes_execution(seeded_db):
    execution_id, result = _run_refund_workflow_to_approval(seeded_db)
    approval_engine.approve(
        approval_id=uuid.UUID(result.approval_request_id), resolved_by="alice", db=seeded_db
    )

    resume_result = runtime.resume(execution_id, seeded_db)
    assert resume_result.status == "COMPLETED"
    execution = seeded_db.get(Execution, execution_id)
    assert execution.status == ExecutionStatus.COMPLETED

    payment = seeded_db.query(Payment).filter_by(payment_id="PAY-9002").one()
    assert payment.status.value == "REFUNDED"
    assert seeded_db.query(Refund).filter_by(payment_id=payment.id).count() == 1


def test_approved_action_not_repeated_on_resume(seeded_db):
    execution_id, result = _run_refund_workflow_to_approval(seeded_db)
    approval_engine.approve(
        approval_id=uuid.UUID(result.approval_request_id), resolved_by="alice", db=seeded_db
    )
    runtime.resume(execution_id, seeded_db)

    refund_requests = (
        seeded_db.query(ToolRequest)
        .filter_by(execution_id=execution_id, tool_name="refund_payment")
        .count()
    )
    assert refund_requests == 1


def test_double_resume_does_not_double_execute(seeded_db):
    execution_id, result = _run_refund_workflow_to_approval(seeded_db)
    approval_engine.approve(
        approval_id=uuid.UUID(result.approval_request_id), resolved_by="alice", db=seeded_db
    )

    first = runtime.resume(execution_id, seeded_db)
    second = runtime.resume(execution_id, seeded_db)
    assert first.status == "COMPLETED"
    assert second.status == "NOOP"

    refund_requests = (
        seeded_db.query(ToolRequest)
        .filter_by(execution_id=execution_id, tool_name="refund_payment")
        .count()
    )
    assert refund_requests == 1


def test_rejected_approval_blocks_execution_on_resume(seeded_db):
    execution_id, result = _run_refund_workflow_to_approval(seeded_db)
    approval_engine.reject(
        approval_id=uuid.UUID(result.approval_request_id),
        resolved_by="bob",
        reason=None,
        db=seeded_db,
    )

    resume_result = runtime.resume(execution_id, seeded_db)
    assert resume_result.status == "BLOCKED"
    execution = seeded_db.get(Execution, execution_id)
    assert execution.status == ExecutionStatus.BLOCKED


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------


def test_cancel_running_execution(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    start = runtime.start_execution(agent_id=agent.id, objective="test objective", db=seeded_db)
    execution_id = uuid.UUID(start.execution_id)

    result = runtime.cancel(execution_id, seeded_db)
    assert result.status == "CANCELLED"
    assert seeded_db.get(Execution, execution_id).status == ExecutionStatus.CANCELLED
    events = [e.event_type.value for e in _events(seeded_db, execution_id)]
    assert events[-1] == "EXECUTION_CANCELLED"


def test_cancel_already_terminal_execution_is_noop(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    execution = Execution(agent_id=agent.id, objective="x", status=ExecutionStatus.COMPLETED)
    seeded_db.add(execution)
    seeded_db.commit()

    result = runtime.cancel(execution.id, seeded_db)
    assert result.status == "NOOP"
    assert seeded_db.get(Execution, execution.id).status == ExecutionStatus.COMPLETED


def test_cancel_while_waiting_approval(seeded_db):
    execution_id, _ = _run_refund_workflow_to_approval(seeded_db)
    result = runtime.cancel(execution_id, seeded_db)
    assert result.status == "CANCELLED"
    assert seeded_db.get(Execution, execution_id).status == ExecutionStatus.CANCELLED


def test_approval_after_cancellation_fails_closed(seeded_db):
    execution_id, result = _run_refund_workflow_to_approval(seeded_db)
    runtime.cancel(execution_id, seeded_db)

    approve_result = approval_engine.approve(
        approval_id=uuid.UUID(result.approval_request_id), resolved_by="alice", db=seeded_db
    )
    assert approve_result.status == "INVALID_STATE"

    payment = seeded_db.query(Payment).filter_by(payment_id="PAY-9002").one()
    assert payment.status.value == "SUCCEEDED"
    assert seeded_db.query(Refund).filter_by(payment_id=payment.id).count() == 0


# ---------------------------------------------------------------------------
# Malicious ticket / block handling
# ---------------------------------------------------------------------------


def test_malicious_ticket_becomes_blocked(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    start = runtime.start_execution(
        agent_id=agent.id, objective="Investigate support ticket TCK-4837", db=seeded_db
    )
    execution_id = uuid.UUID(start.execution_id)

    r1 = runtime.step(execution_id, seeded_db)
    assert r1.status == "EXECUTED" and r1.tool_name == "get_support_ticket"

    r2 = runtime.step(execution_id, seeded_db)
    assert r2.status == "BLOCKED"

    execution = seeded_db.get(Execution, execution_id)
    assert execution.status == ExecutionStatus.BLOCKED

    incident = seeded_db.query(SecurityIncident).filter_by(execution_id=execution_id).one()
    assert incident.status.value == "OPEN"

    # Blocked runtime cannot resume or step further.
    assert runtime.step(execution_id, seeded_db).status == "NOOP"
    assert runtime.resume(execution_id, seeded_db).status == "NOOP"

    steps = _steps(seeded_db, execution_id)
    assert len(steps) == 2  # get_support_ticket + the blocked send_external_email attempt
    ticket_step, blocked_step = steps
    assert blocked_step.input["sources"][0]["trust"] == "UNTRUSTED"


def test_normal_ticket_not_blocked(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    start = runtime.start_execution(
        agent_id=agent.id, objective="Investigate support ticket TCK-4820", db=seeded_db
    )
    execution_id = uuid.UUID(start.execution_id)

    r1 = runtime.step(execution_id, seeded_db)
    assert r1.status == "EXECUTED" and r1.tool_name == "get_support_ticket"

    # A normal ticket gives the naive planner nothing that looks like an
    # external-send instruction to follow, so it never proposes the risky
    # action at all -- the workflow just completes.
    r2 = runtime.step(execution_id, seeded_db)
    assert r2.status == "COMPLETED"
    assert seeded_db.get(Execution, execution_id).status == ExecutionStatus.COMPLETED
    assert seeded_db.query(SecurityIncident).filter_by(execution_id=execution_id).count() == 0


# ---------------------------------------------------------------------------
# Safe / production deploy demos
# ---------------------------------------------------------------------------


def test_staging_deploy_completes(seeded_db):
    agent = _agent(seeded_db, "devops-agent")
    start = runtime.start_execution(
        agent_id=agent.id,
        objective="Deploy checkout-service version 2.0 to staging",
        db=seeded_db,
    )
    execution_id = uuid.UUID(start.execution_id)

    r1 = runtime.step(execution_id, seeded_db)
    assert r1.status == "EXECUTED" and r1.tool_name == "get_deployment"
    r2 = runtime.step(execution_id, seeded_db)
    assert r2.status == "EXECUTED" and r2.tool_name == "deploy_staging"
    r3 = runtime.step(execution_id, seeded_db)
    assert r3.status == "COMPLETED"
    assert seeded_db.get(Execution, execution_id).status == ExecutionStatus.COMPLETED

    deployments = seeded_db.query(Deployment).filter(Deployment.version == "2.0").count()
    assert deployments == 1


def test_production_deploy_requires_approval_then_completes_exactly_once(seeded_db):
    agent = _agent(seeded_db, "devops-agent")
    start = runtime.start_execution(
        agent_id=agent.id,
        objective="Deploy checkout-service version 3.0 to production",
        db=seeded_db,
    )
    execution_id = uuid.UUID(start.execution_id)

    runtime.step(execution_id, seeded_db)  # get_deployment
    result = runtime.step(execution_id, seeded_db)  # deploy_production -> approval
    assert result.status == "WAITING_APPROVAL"

    approval_engine.approve(
        approval_id=uuid.UUID(result.approval_request_id), resolved_by="ops-lead", db=seeded_db
    )
    resume_result = runtime.resume(execution_id, seeded_db)
    assert resume_result.status == "COMPLETED"

    deployments = seeded_db.query(Deployment).filter(Deployment.version == "3.0").count()
    assert deployments == 1


# ---------------------------------------------------------------------------
# Audit / step ordering
# ---------------------------------------------------------------------------


def test_execution_audit_ordering(seeded_db):
    execution_id, result = _run_refund_workflow_to_approval(seeded_db)
    approval_engine.approve(
        approval_id=uuid.UUID(result.approval_request_id), resolved_by="alice", db=seeded_db
    )
    runtime.resume(execution_id, seeded_db)

    events = _events(seeded_db, execution_id)
    assert [e.sequence for e in events] == list(range(1, len(events) + 1))
    event_types = [e.event_type.value for e in events]
    assert event_types[0] == "EXECUTION_STARTED"
    assert "EXECUTION_STEP_STARTED" in event_types
    assert "EXECUTION_WAITING_APPROVAL" in event_types
    assert "EXECUTION_RESUMED" in event_types
    assert event_types[-1] == "EXECUTION_COMPLETED"
    assert event_types.index("EXECUTION_WAITING_APPROVAL") < event_types.index("EXECUTION_RESUMED")


def test_step_sequence_ordering(seeded_db):
    execution_id, _ = _run_refund_workflow_to_approval(seeded_db)
    steps = _steps(seeded_db, execution_id)
    assert [s.sequence for s in steps] == list(range(1, len(steps) + 1))


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


def test_concurrent_step_calls_cannot_run_same_step_twice(seeded_db, db_engine):
    # Two callers starting at (as close to) the same instant as possible:
    # step() claims Execution.stepping non-blockingly before doing any
    # planning, so exactly one of them ever reaches the planner/gateway for
    # this unit of work -- the other gets CONFLICT immediately.
    agent = _agent(seeded_db, "support-agent")
    start = runtime.start_execution(
        agent_id=agent.id,
        objective="Investigate duplicate payment for CUST-1001 and refund the duplicate",
        db=seeded_db,
    )
    execution_id = uuid.UUID(start.execution_id)

    barrier = Barrier(2)

    def call_step():
        with Session(db_engine) as session:
            barrier.wait(timeout=5)
            return runtime.step(execution_id, session)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: call_step(), range(2)))

    assert sorted(r.status for r in results) == ["CONFLICT", "EXECUTED"]

    seeded_db.expire_all()
    steps = _steps(seeded_db, execution_id)
    assert len(steps) == 1
    assert steps[0].input["tool_name"] == "read_customer"
    read_customer_requests = (
        seeded_db.query(ToolRequest)
        .filter_by(execution_id=execution_id, tool_name="read_customer")
        .count()
    )
    assert read_customer_requests == 1
    assert seeded_db.get(Execution, execution_id).stepping is False


def test_concurrent_resume_cannot_double_run(seeded_db, db_engine):
    execution_id, result = _run_refund_workflow_to_approval(seeded_db)
    approval_engine.approve(
        approval_id=uuid.UUID(result.approval_request_id), resolved_by="alice", db=seeded_db
    )

    barrier = Barrier(2)

    def call_resume():
        with Session(db_engine) as session:
            barrier.wait(timeout=5)
            return runtime.resume(execution_id, session)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: call_resume(), range(2)))

    assert sorted(r.status for r in results) == ["COMPLETED", "CONFLICT"]

    seeded_db.expire_all()
    refund_requests = (
        seeded_db.query(ToolRequest)
        .filter_by(execution_id=execution_id, tool_name="refund_payment")
        .count()
    )
    assert refund_requests == 1
    assert seeded_db.get(Execution, execution_id).stepping is False


# ---------------------------------------------------------------------------
# Regression: cancellation racing an in-flight step must never let the tool
# execute. ToolGateway's own NON_EXECUTABLE_STATUSES set did not originally
# include CANCELLED (a milestone 8 status), so a cancel() landing between the
# runtime's ExecutionStep claim and the gateway's own fresh status read could
# let the tool run anyway. See ToolGateway.NON_EXECUTABLE_STATUSES.
# ---------------------------------------------------------------------------


def test_cancellation_race_prevents_tool_execution_deterministic(seeded_db, monkeypatch):
    agent = _agent(seeded_db, "devops-agent")
    start = runtime.start_execution(
        agent_id=agent.id,
        objective="Deploy checkout-service version 8.8.8 to staging",
        db=seeded_db,
    )
    execution_id = uuid.UUID(start.execution_id)
    r1 = runtime.step(execution_id, seeded_db)
    assert r1.status == "EXECUTED" and r1.tool_name == "get_deployment"

    original_claim_step = AgentRuntime._claim_step

    def racing_claim_step(db, exec_id, step_type, input_data):
        step = original_claim_step(db, exec_id, step_type, input_data)
        if step is not None and input_data.get("tool_name") == "deploy_staging":
            # Simulate a concurrent cancel() landing right after the step is
            # claimed (and committed) but before the gateway call runs.
            cancel_result = runtime.cancel(exec_id, seeded_db)
            assert cancel_result.status == "CANCELLED"
        return step

    monkeypatch.setattr(AgentRuntime, "_claim_step", staticmethod(racing_claim_step))

    r2 = runtime.step(execution_id, seeded_db)
    assert r2.status == "FAILED"
    assert "CANCELLED" in (r2.reason or "")

    seeded_db.expire_all()
    execution = seeded_db.get(Execution, execution_id)
    assert execution.status == ExecutionStatus.CANCELLED
    assert seeded_db.query(Deployment).filter_by(version="8.8.8").count() == 0
    tool_requests = (
        seeded_db.query(ToolRequest)
        .filter_by(execution_id=execution_id, tool_name="deploy_staging")
        .all()
    )
    assert all(tr.status.value != "EXECUTED" for tr in tool_requests)


def test_cancellation_race_stress_with_real_threads(db_engine, seeded_db):
    # Real concurrent sessions, repeated: fire step() and cancel() from
    # separate connections at (as close to) the same instant, many times,
    # and assert the safety invariant holds on every single iteration --
    # cancellation must never coexist with a side effect it should have
    # prevented, regardless of which side wins the race.
    agent_id = _agent(seeded_db, "devops-agent").id

    for i in range(15):
        with Session(db_engine) as setup:
            start = runtime.start_execution(
                agent_id=agent_id,
                objective=f"Deploy checkout-service version 7.{i}.0 to staging",
                db=setup,
            )
            execution_id = uuid.UUID(start.execution_id)
            first = runtime.step(execution_id, setup)
            assert first.status == "EXECUTED"

        barrier = Barrier(2)

        def call_step():
            with Session(db_engine) as session:
                barrier.wait(timeout=5)
                return runtime.step(execution_id, session)

        def call_cancel():
            with Session(db_engine) as session:
                barrier.wait(timeout=5)
                return runtime.cancel(execution_id, session)

        with ThreadPoolExecutor(max_workers=2) as executor:
            step_future = executor.submit(call_step)
            cancel_future = executor.submit(call_cancel)
            step_future.result(timeout=10)
            cancel_result = cancel_future.result(timeout=10)

        with Session(db_engine) as check:
            execution = check.get(Execution, execution_id)
            deployed = (
                check.query(Deployment).filter_by(version=f"7.{i}.0").count() > 0
            )
            executed_requests = (
                check.query(ToolRequest)
                .filter_by(
                    execution_id=execution_id,
                    tool_name="deploy_staging",
                    status=ToolRequestStatus.EXECUTED,
                )
                .count()
            )

            if execution.status == ExecutionStatus.CANCELLED:
                # Cancellation won (or the step lost/conflicted): no deploy
                # side effect may exist under a CANCELLED execution.
                assert not deployed, f"iteration {i}: deploy happened under CANCELLED"
                assert executed_requests == 0
            else:
                # The step won outright before cancel's CAS landed: cancel
                # must have been a clean NOOP, never silently discarded.
                assert cancel_result.status in ("CANCELLED", "NOOP")
                if cancel_result.status == "NOOP":
                    assert execution.status in (
                        ExecutionStatus.RUNNING,
                        ExecutionStatus.WAITING_APPROVAL,
                        ExecutionStatus.COMPLETED,
                        ExecutionStatus.FAILED,
                        ExecutionStatus.BLOCKED,
                    )

            assert execution.stepping is False, f"iteration {i}: stepping flag left claimed"


def test_concurrent_step_cannot_double_deploy_staging(db_engine, seeded_db):
    # deploy_staging has no tool-layer idempotency key (unlike
    # refund_payment). The only thing preventing a concurrency-driven
    # double-deploy is the runtime's Execution.stepping claim -- verify it
    # holds under real concurrent sessions, repeated.
    agent_id = _agent(seeded_db, "devops-agent").id

    for i in range(10):
        with Session(db_engine) as setup:
            start = runtime.start_execution(
                agent_id=agent_id,
                objective=f"Deploy checkout-service version 6.{i}.0 to staging",
                db=setup,
            )
            execution_id = uuid.UUID(start.execution_id)
            first = runtime.step(execution_id, setup)
            assert first.status == "EXECUTED"

        barrier = Barrier(2)

        def call_step():
            with Session(db_engine) as session:
                barrier.wait(timeout=5)
                return runtime.step(execution_id, session)

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: call_step(), range(2)))

        assert sorted(r.status for r in results) == ["CONFLICT", "EXECUTED"]

        with Session(db_engine) as check:
            deployments = check.query(Deployment).filter_by(version=f"6.{i}.0").count()
            assert deployments == 1, f"iteration {i}: expected one deploy, got {deployments}"
