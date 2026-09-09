import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import IncidentStatus, IncidentType, RiskLevel


class SecurityIncident(Base):
    __tablename__ = "security_incidents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    execution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("executions.id"), index=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id"), index=True)
    tool_request_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tool_requests.id"), index=True)
    risk_assessment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("risk_assessments.id"), index=True
    )
    incident_type: Mapped[IncidentType] = mapped_column(
        Enum(IncidentType, native_enum=False, length=32, create_constraint=True), index=True
    )
    severity: Mapped[RiskLevel] = mapped_column(
        Enum(RiskLevel, native_enum=False, length=16, create_constraint=True), index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String(2000))
    indicators: Mapped[list[str]] = mapped_column(JSONB, default=list)
    status: Mapped[IncidentStatus] = mapped_column(
        Enum(IncidentStatus, native_enum=False, length=16, create_constraint=True),
        default=IncidentStatus.OPEN,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
