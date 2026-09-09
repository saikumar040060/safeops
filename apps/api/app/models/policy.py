import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import PolicyAction


class Policy(Base):
    __tablename__ = "policies"
    __table_args__ = (UniqueConstraint("policy_key", name="uq_policies_policy_key"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String(2000), default=None)
    policy_key: Mapped[str] = mapped_column(String(255), index=True)
    agent_type: Mapped[str | None] = mapped_column(String(100), index=True, default=None)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agents.id"), index=True, default=None
    )
    tool_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tools.id"), index=True, default=None
    )
    priority: Mapped[int] = mapped_column(Integer, default=100)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    action: Mapped[PolicyAction] = mapped_column(
        Enum(PolicyAction, native_enum=False, length=32, create_constraint=True), index=True
    )
    conditions: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
