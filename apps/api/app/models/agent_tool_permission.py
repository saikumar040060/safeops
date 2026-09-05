import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import PermissionType


class AgentToolPermission(Base):
    __tablename__ = "agent_tool_permissions"
    __table_args__ = (
        UniqueConstraint("agent_id", "tool_id", name="uq_agent_tool_permissions_agent_tool"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id"), index=True)
    tool_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tools.id"), index=True)
    permission: Mapped[PermissionType] = mapped_column(
        Enum(PermissionType, native_enum=False, length=16, create_constraint=True), index=True
    )
    constraints: Mapped[dict | None] = mapped_column(JSONB, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
