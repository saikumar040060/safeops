import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import PolicyAction


class PolicyDecision(Base):
    __tablename__ = "policy_decisions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    execution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("executions.id"), index=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id"), index=True)
    tool_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tools.id"), index=True)
    tool_request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tool_requests.id"), index=True)
    decision: Mapped[PolicyAction] = mapped_column(
        Enum(PolicyAction, native_enum=False, length=32, create_constraint=True), index=True
    )
    matched_policy_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("policies.id"), index=True, default=None
    )
    matched_policy_key: Mapped[str | None] = mapped_column(String(255), default=None)
    reason: Mapped[str] = mapped_column(String(2000))
    evaluated_context: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
