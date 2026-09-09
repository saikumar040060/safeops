import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import OperatorRole

if TYPE_CHECKING:
    from app.models.operator_token import OperatorToken


class Operator(Base):
    """An authenticated human principal. Never created implicitly by a
    request -- only by seed data (demo mode) or an out-of-band admin
    action, so `resolved_by`/audit actor identity always traces back to a
    real, provisioned account rather than a caller-supplied string.
    """

    __tablename__ = "operators"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    role: Mapped[OperatorRole] = mapped_column(
        Enum(OperatorRole, native_enum=False, length=16, create_constraint=True),
        default=OperatorRole.VIEWER,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tokens: Mapped[list["OperatorToken"]] = relationship(back_populates="operator")
