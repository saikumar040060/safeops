import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import ExecutionStatus, StepStatus, StepType


class ExecutionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    objective: str
    status: ExecutionStatus
    initial_context: dict[str, Any]
    created_at: datetime
    started_at: datetime
    completed_at: datetime | None


class ExecutionStepRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    execution_id: uuid.UUID
    sequence: int
    step_type: StepType
    status: StepStatus
    tool_request_id: uuid.UUID | None
    input: dict[str, Any]
    output: dict[str, Any] | None
    created_at: datetime
    completed_at: datetime | None
