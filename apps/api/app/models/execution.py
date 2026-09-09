import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import ExecutionStatus

if TYPE_CHECKING:
    from app.models.agent import Agent
    from app.models.approval_request import ApprovalRequest
    from app.models.audit_event import AuditEvent


class Execution(Base):
    __tablename__ = "executions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id"), index=True)
    objective: Mapped[str] = mapped_column(String(4000))
    status: Mapped[ExecutionStatus] = mapped_column(
        Enum(ExecutionStatus, native_enum=False, length=32, create_constraint=True),
        default=ExecutionStatus.RUNNING,
        index=True,
    )
    # Caller-supplied trusted metadata / untrusted sources from
    # AgentRuntime.start_execution, persisted so later step()/resume() calls
    # (separate requests) can reconstruct full planner context from durable
    # state rather than in-memory state that wouldn't survive a process
    # boundary.
    initial_context: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # Lease-based claim AgentRuntime.step()/resume() use to serialize the
    # whole plan-execute-finalize critical section for one execution.
    # Deliberately plain transactional row data rather than a Postgres
    # session-level advisory lock: SQLAlchemy sessions do not pin one
    # physical connection across the many small commits that section makes,
    # so a lock acquired on one connection could be "released" on another,
    # never actually freeing it. `stepping_claim_id` + `stepping_claimed_at`
    # turn the old permanent boolean into a TTL'd lease: a claim older than
    # STEPPING_LEASE_TTL is treated as stale and safely recoverable by a new
    # claimant (see agent_runtime.py for the full CAS/ownership argument),
    # closing the "crashed process leaves stepping=True forever" liveness
    # bug the plain boolean had.
    stepping: Mapped[bool] = mapped_column(Boolean, default=False)
    stepping_claim_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, default=None)
    stepping_claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    agent: Mapped["Agent"] = relationship(back_populates="executions")
    audit_events: Mapped[list["AuditEvent"]] = relationship(back_populates="execution")
    approval_requests: Mapped[list["ApprovalRequest"]] = relationship(back_populates="execution")
