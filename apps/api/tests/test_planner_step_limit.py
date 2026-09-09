"""Milestone 10 section 8: MAX_EXECUTION_STEPS bound. Fails closed before
ever calling the planner, regardless of what the planner would have done."""

from app.models import AuditEvent, Execution, ExecutionStep
from app.models.enums import AuditEventType, ExecutionStatus, StepStatus, StepType
from app.services.agent_runtime import MAX_EXECUTION_STEPS, AgentRuntime

runtime = AgentRuntime()


def _agent(db, name):
    from app.models import Agent

    return db.query(Agent).filter_by(name=name).one()


def test_execution_at_step_limit_fails_closed_without_calling_planner(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    start = runtime.start_execution(
        agent_id=agent.id,
        objective="Objective the planner would never resolve normally",
        db=seeded_db,
    )
    import uuid

    execution_id = uuid.UUID(start.execution_id)

    # Pad history to exactly MAX_EXECUTION_STEPS with harmless completed
    # steps -- the bound is checked purely on step *count*, independent of
    # what those steps contain.
    for seq in range(1, MAX_EXECUTION_STEPS + 1):
        seeded_db.add(
            ExecutionStep(
                execution_id=execution_id,
                sequence=seq,
                step_type=StepType.TOOL_CALL,
                status=StepStatus.COMPLETED,
                input={"tool_name": "get_payments", "arguments": {}},
                output={"status": "EXECUTED"},
            )
        )
    seeded_db.commit()

    result = runtime.step(execution_id, seeded_db)

    assert result.status == "FAILED"
    assert "MAX_EXECUTION_STEPS" in (result.reason or "")

    execution = seeded_db.get(Execution, execution_id)
    assert execution.status == ExecutionStatus.FAILED

    final_step = (
        seeded_db.query(ExecutionStep)
        .filter_by(execution_id=execution_id, sequence=MAX_EXECUTION_STEPS + 1)
        .one()
    )
    assert final_step.status == StepStatus.FAILED
    assert final_step.output["code"] == "MAX_STEPS_EXCEEDED"

    failed_events = (
        seeded_db.query(AuditEvent)
        .filter_by(execution_id=execution_id, event_type=AuditEventType.EXECUTION_FAILED)
        .all()
    )
    assert len(failed_events) == 1
    assert failed_events[0].event_metadata["code"] == "MAX_STEPS_EXCEEDED"


def test_execution_below_step_limit_is_unaffected(seeded_db):
    agent = _agent(seeded_db, "support-agent")
    start = runtime.start_execution(
        agent_id=agent.id,
        objective="Investigate duplicate payment for CUST-1001 and refund the duplicate",
        db=seeded_db,
    )
    import uuid

    execution_id = uuid.UUID(start.execution_id)
    result = runtime.step(execution_id, seeded_db)
    assert result.status == "EXECUTED"
    assert result.tool_name == "read_customer"
