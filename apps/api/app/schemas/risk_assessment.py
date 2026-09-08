import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models.enums import PolicyAction, RiskLevel


class RiskAssessmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    execution_id: uuid.UUID
    agent_id: uuid.UUID
    tool_request_id: uuid.UUID
    tool_id: uuid.UUID
    policy_decision_id: uuid.UUID | None
    risk_score: int
    risk_level: RiskLevel
    signals: list[str]
    reason_codes: list[str]
    assessment_context: dict[str, Any]
    recommended_action: PolicyAction
    created_at: datetime
