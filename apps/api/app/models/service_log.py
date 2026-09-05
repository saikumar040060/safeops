import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import LogLevel

if TYPE_CHECKING:
    from app.models.service import Service


class ServiceLog(Base):
    __tablename__ = "service_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    service_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("services.id"), index=True)
    level: Mapped[LogLevel] = mapped_column(
        Enum(LogLevel, native_enum=False, length=16, create_constraint=True), index=True
    )
    message: Mapped[str] = mapped_column(String(2000))
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    service: Mapped["Service"] = relationship(back_populates="logs")
