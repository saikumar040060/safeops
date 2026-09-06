import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import StepStatus, StepType


class ExecutionStep(Base):
    __tablename__ = "execution_steps"
    __table_args__ = (
        UniqueConstraint("execution_id", "sequence", name="uq_execution_steps_execution_sequence"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    execution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("executions.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    step_type: Mapped[StepType] = mapped_column(
        Enum(StepType, native_enum=False, length=16, create_constraint=True), index=True
    )
    tool_request_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tool_requests.id"), index=True, default=None
    )
    status: Mapped[StepStatus] = mapped_column(
        Enum(StepStatus, native_enum=False, length=20, create_constraint=True),
        default=StepStatus.PENDING,
        index=True,
    )
    input: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
