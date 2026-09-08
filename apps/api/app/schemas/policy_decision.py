import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import PolicyAction


class PolicyDecisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    execution_id: uuid.UUID
    agent_id: uuid.UUID
    tool_id: uuid.UUID
    tool_request_id: uuid.UUID
    decision: PolicyAction
    matched_policy_id: uuid.UUID | None
    matched_policy_key: str | None
    reason: str
    created_at: datetime
