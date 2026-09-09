import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import DeploymentEnvironment

if TYPE_CHECKING:
    from app.models.service import Service


class Deployment(Base):
    __tablename__ = "deployments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    service_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("services.id"), index=True)
    environment: Mapped[DeploymentEnvironment] = mapped_column(
        Enum(DeploymentEnvironment, native_enum=False, length=16, create_constraint=True),
        index=True,
    )
    version: Mapped[str] = mapped_column(String(64))
    # Nullable + unique so historical rows (created before this column
    # existed) keep NULL -- Postgres treats multiple NULLs in a unique
    # index as distinct, so uniqueness is only enforced going forward for
    # rows that actually supply a key. See tools/devops.py::_deploy for how
    # a retried/re-executed deploy with the same key replays the existing
    # row instead of inserting a duplicate.
    idempotency_key: Mapped[str | None] = mapped_column(
        String(255), unique=True, index=True, default=None
    )
    deployed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    service: Mapped["Service"] = relationship(back_populates="deployments")
