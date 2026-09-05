import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import ToolRequestStatus


class ToolRequest(Base):
    __tablename__ = "tool_requests"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    execution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("executions.id"), index=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id"), index=True)
    tool_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tools.id"), index=True, default=None
    )
    tool_name: Mapped[str] = mapped_column(String(255), index=True)
    arguments: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[ToolRequestStatus] = mapped_column(
        Enum(ToolRequestStatus, native_enum=False, length=16, create_constraint=True), index=True
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
