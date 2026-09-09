import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.agent import Agent
    from app.models.operator import Operator


class IntegrationAgentMapping(Base):
    """Grants one INTEGRATION-type Operator permission to act as one
    SafeOps Agent. A caller-supplied `safeops_agent_id` in an external
    request is only honored if a row exists here for the *authenticated*
    integration principal -- it can never simply claim any agent by
    changing the request JSON (see Milestone 11 threat test: cross-agent
    impersonation). This is checked before the request reaches
    ToolGateway; ToolGateway's own AgentToolPermission check still applies
    independently underneath regardless.
    """

    __tablename__ = "integration_agent_mappings"
    __table_args__ = (
        UniqueConstraint("operator_id", "agent_id", name="uq_integration_agent_mapping"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    operator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("operators.id"), index=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    operator: Mapped["Operator"] = relationship(back_populates="agent_mappings")
    agent: Mapped["Agent"] = relationship()
