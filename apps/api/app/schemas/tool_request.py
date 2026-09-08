import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import ToolRequestStatus


class ToolRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    execution_id: uuid.UUID
    agent_id: uuid.UUID
    tool_id: uuid.UUID | None
    tool_name: str
    arguments: dict[str, Any]
    status: ToolRequestStatus
    requested_at: datetime
    completed_at: datetime | None
    result: dict[str, Any] | None
    error: dict[str, Any] | None
