import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import ExternalActionStatus, IntegrationType

if TYPE_CHECKING:
    from app.models.agent import Agent
    from app.models.approval_request import ApprovalRequest
    from app.models.execution import Execution
    from app.models.operator import Operator
    from app.models.tool_request import ToolRequest


class ExternalActionRequest(Base):
    """Durable idempotency + correlation record for one externally
    submitted action (via the generic API or the MCP adapter). This is
    deliberately thin -- it does not duplicate ToolRequest/ApprovalRequest
    semantics, only tracks enough to (a) make retries with the same
    external_request_id idempotent and (b) let an external caller
    correlate its own request id back to what SafeOps actually did.

    Uniqueness is scoped per authenticated integration principal
    (operator_id), not globally -- two different integrations may each
    use "req-1" as their own external_request_id without colliding.
    """

    __tablename__ = "external_action_requests"
    __table_args__ = (
        UniqueConstraint(
            "operator_id", "external_request_id", name="uq_external_action_request_idempotency"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    operator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("operators.id"), index=True)
    integration_type: Mapped[IntegrationType] = mapped_column(
        Enum(IntegrationType, native_enum=False, length=16, create_constraint=True)
    )
    external_request_id: Mapped[str] = mapped_column(String(255), index=True)
    # Caller-supplied display/reference string only -- never trusted for
    # authorization. The authenticated identity is operator_id above.
    external_agent_id: Mapped[str | None] = mapped_column(String(255), default=None)
    safeops_agent_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agents.id"), index=True)
    execution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("executions.id"), index=True)
    tool_name: Mapped[str] = mapped_column(String(255))
    tool_request_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tool_requests.id"), default=None
    )
    approval_request_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("approval_requests.id"), default=None
    )
    payload_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[ExternalActionStatus] = mapped_column(
        Enum(ExternalActionStatus, native_enum=False, length=20, create_constraint=True),
        default=ExternalActionStatus.RECEIVED,
        index=True,
    )
    result_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
    error_code: Mapped[str | None] = mapped_column(String(64), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    operator: Mapped["Operator"] = relationship()
    safeops_agent: Mapped["Agent"] = relationship()
    execution: Mapped["Execution"] = relationship()
    tool_request: Mapped["ToolRequest | None"] = relationship()
    approval_request: Mapped["ApprovalRequest | None"] = relationship()
