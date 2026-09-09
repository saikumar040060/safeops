import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import PolicyAction, RiskLevel


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"
    __table_args__ = (
        CheckConstraint("risk_score >= 0 AND risk_score <= 100", name="ck_risk_assessments_score"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    execution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("executions.id"), index=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id"), index=True)
    tool_request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tool_requests.id"), index=True)
    tool_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tools.id"), index=True)
    policy_decision_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("policy_decisions.id"), index=True, default=None
    )
    risk_score: Mapped[int] = mapped_column(Integer)
    risk_level: Mapped[RiskLevel] = mapped_column(
        Enum(RiskLevel, native_enum=False, length=16, create_constraint=True), index=True
    )
    signals: Mapped[list[str]] = mapped_column(JSONB, default=list)
    reason_codes: Mapped[list[str]] = mapped_column(JSONB, default=list)
    assessment_context: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    recommended_action: Mapped[PolicyAction] = mapped_column(
        Enum(PolicyAction, native_enum=False, length=32, create_constraint=True), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
