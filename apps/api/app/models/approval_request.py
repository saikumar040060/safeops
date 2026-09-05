import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import ApprovalStatus, RiskLevel

if TYPE_CHECKING:
    from app.models.agent import Agent
    from app.models.execution import Execution


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    execution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("executions.id"), index=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id"), index=True)
    tool_name: Mapped[str] = mapped_column(String(255), index=True)
    arguments: Mapped[dict] = mapped_column(JSONB, default=dict)
    risk_level: Mapped[RiskLevel] = mapped_column(
        Enum(RiskLevel, native_enum=False, length=16, create_constraint=True)
    )
    reason: Mapped[str] = mapped_column(String(2000))
    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus, native_enum=False, length=16, create_constraint=True),
        default=ApprovalStatus.PENDING,
        index=True,
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    resolved_by: Mapped[str | None] = mapped_column(String(255), default=None)

    execution: Mapped["Execution"] = relationship(back_populates="approval_requests")
    agent: Mapped["Agent"] = relationship(back_populates="approval_requests")
