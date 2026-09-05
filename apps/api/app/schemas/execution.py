import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import ExecutionStatus


class ExecutionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    objective: str
    status: ExecutionStatus
    created_at: datetime
    started_at: datetime
    completed_at: datetime | None
