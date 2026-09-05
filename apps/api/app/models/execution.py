import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    agent: Mapped["Agent"] = relationship(back_populates="executions")
    audit_events: Mapped[list["AuditEvent"]] = relationship(back_populates="execution")
    approval_requests: Mapped[list["ApprovalRequest"]] = relationship(back_populates="execution")
