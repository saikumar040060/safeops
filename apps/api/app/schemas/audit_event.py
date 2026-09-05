import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import AuditEventType


class AuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    execution_id: uuid.UUID
    sequence: int
    event_type: AuditEventType
    actor: str
    event_metadata: dict[str, Any]
    timestamp: datetime
