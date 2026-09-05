import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Agent, ApprovalRequest, AuditEvent, Execution, Tool
from app.models.enums import (
    AgentStatus,
    ApprovalStatus,
    AuditEventType,
    ExecutionStatus,
    RiskLevel,
)


def test_agent_and_tool_creation_with_defaults(db_session):
    agent = Agent(name="test-agent", type="support")
    tool = Tool(name="test_tool", risk_category=RiskLevel.MEDIUM)
    db_session.add_all([agent, tool])
    db_session.commit()

    assert agent.id is not None
    assert agent.status == AgentStatus.ACTIVE
    assert agent.risk_level == RiskLevel.LOW
    assert agent.created_at is not None
    assert agent.updated_at is not None
    assert tool.enabled is True


def test_agent_name_uniqueness(db_session):
    db_session.add(Agent(name="dup-agent", type="support"))
    db_session.commit()

    db_session.add(Agent(name="dup-agent", type="devops"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_tool_name_uniqueness(db_session):
    db_session.add(Tool(name="dup_tool"))
    db_session.commit()

    db_session.add(Tool(name="dup_tool"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_invalid_status_enum_rejected_by_check_constraint(db_session):
    agent = Agent(name="enum-agent", type="support")
    agent.status = "NOT_A_STATUS"
    db_session.add(agent)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_execution_relationship_to_agent(db_session):
    agent = Agent(name="rel-agent", type="support")
    db_session.add(agent)
    db_session.flush()

    execution = Execution(
        agent_id=agent.id,
        objective="Resolve duplicate payment for CUST-1001",
        status=ExecutionStatus.WAITING_APPROVAL,
    )
    db_session.add(execution)
    db_session.commit()
    db_session.refresh(agent)

    assert execution in agent.executions
    assert execution.agent.id == agent.id
    assert execution.status == ExecutionStatus.WAITING_APPROVAL


def test_audit_event_and_approval_request_relationships(db_session):
    agent = Agent(name="audit-agent", type="support")
    tool = Tool(name="refund_payment_test", risk_category=RiskLevel.HIGH)
    db_session.add_all([agent, tool])
    db_session.flush()

    execution = Execution(agent_id=agent.id, objective="Investigate refund")
    db_session.add(execution)
    db_session.flush()

    event = AuditEvent(
        execution_id=execution.id,
        sequence=1,
        event_type=AuditEventType.APPROVAL_REQUESTED,
        actor=f"agent:{agent.name}",
        event_metadata={"tool": tool.name},
    )
    approval = ApprovalRequest(
        execution_id=execution.id,
        agent_id=agent.id,
        tool_name=tool.name,
        arguments={"payment_id": "PAY-9001", "amount": 750},
        risk_level=RiskLevel.HIGH,
        reason="Duplicate transaction detected",
    )
    db_session.add_all([event, approval])
    db_session.commit()
    db_session.refresh(execution)

    assert event in execution.audit_events
    assert approval in execution.approval_requests
    assert approval.agent.id == agent.id
    assert approval.status == ApprovalStatus.PENDING
    assert approval.arguments["amount"] == 750
    assert event.event_metadata["tool"] == "refund_payment_test"


def test_audit_event_sequence_unique_per_execution(db_session):
    agent = Agent(name="seq-agent", type="support")
    db_session.add(agent)
    db_session.flush()
    execution = Execution(agent_id=agent.id, objective="test")
    db_session.add(execution)
    db_session.flush()

    db_session.add(
        AuditEvent(
            execution_id=execution.id,
            sequence=1,
            event_type=AuditEventType.EXECUTION_STARTED,
            actor="system",
        )
    )
    db_session.commit()

    db_session.add(
        AuditEvent(
            execution_id=execution.id,
            sequence=1,
            event_type=AuditEventType.EXECUTION_COMPLETED,
            actor="system",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
