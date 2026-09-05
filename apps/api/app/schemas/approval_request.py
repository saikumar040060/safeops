import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import ApprovalStatus, RiskLevel


class ApprovalRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    execution_id: uuid.UUID
    agent_id: uuid.UUID
    tool_request_id: uuid.UUID
    policy_decision_id: uuid.UUID
    tool_name: str
    approved_arguments: dict[str, Any]
    risk_level: RiskLevel
    reason: str
    status: ApprovalStatus
    requested_at: datetime
    expires_at: datetime
    resolved_at: datetime | None
    resolved_by: str | None
    executed_at: datetime | None
