import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import OperatorRole, PrincipalType

if TYPE_CHECKING:
    from app.models.integration_agent_mapping import IntegrationAgentMapping
    from app.models.operator_token import OperatorToken


class Operator(Base):
    """An authenticated principal -- either a human (`principal_type`
    OPERATOR, gated by `role`) or a machine integration (`principal_type`
    INTEGRATION, gated by `integration_scopes` instead). Never created
    implicitly by a request -- only by seed data (demo mode) or an
    out-of-band admin action, so `resolved_by`/audit actor identity always
    traces back to a real, provisioned account rather than a
    caller-supplied string.

    An INTEGRATION row always keeps `role=VIEWER` as defense in depth: even
    if some future code path mistakenly used the human role-based
    `require_permission` check against an integration principal instead of
    the scope-based `require_scope` check, VIEWER can only read -- it can
    never approve or execute. `role` and `integration_scopes` are
    deliberately two independent authorization dimensions that are never
    combined. This is a real, DB-enforced CHECK constraint
    (`ck_operators_integration_role_viewer`), not just a seeding
    convention -- found missing during the Milestone 11 security review,
    where the invariant was documented here but nothing actually stopped
    a future INTEGRATION row from being created with an elevated role.
    """

    __tablename__ = "operators"
    __table_args__ = (
        CheckConstraint(
            "principal_type != 'INTEGRATION' OR role = 'VIEWER'",
            name="ck_operators_integration_role_viewer",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[OperatorRole] = mapped_column(
        Enum(OperatorRole, native_enum=False, length=16, create_constraint=True),
        default=OperatorRole.VIEWER,
        index=True,
    )
    principal_type: Mapped[PrincipalType] = mapped_column(
        Enum(PrincipalType, native_enum=False, length=16, create_constraint=True),
        default=PrincipalType.OPERATOR,
        index=True,
    )
    # Only meaningful when principal_type == INTEGRATION. Never includes
    # "approvals:approve" by default -- see require_scope() in
    # app/core/security.py, which is the only thing that reads this.
    integration_scopes: Mapped[list[str]] = mapped_column(JSONB, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tokens: Mapped[list["OperatorToken"]] = relationship(back_populates="operator")
    agent_mappings: Mapped[list["IntegrationAgentMapping"]] = relationship(
        back_populates="operator"
    )
