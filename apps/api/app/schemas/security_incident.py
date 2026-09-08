import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import IncidentStatus, IncidentType, RiskLevel


class SecurityIncidentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    execution_id: uuid.UUID
    agent_id: uuid.UUID
    tool_request_id: uuid.UUID
    risk_assessment_id: uuid.UUID
    incident_type: IncidentType
    severity: RiskLevel
    title: str
    description: str
    indicators: list[str]
    status: IncidentStatus
    created_at: datetime
    resolved_at: datetime | None
