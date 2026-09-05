import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import AgentStatus, RiskLevel


class AgentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    type: str
    description: str | None
    status: AgentStatus
    risk_level: RiskLevel
    created_at: datetime
    updated_at: datetime
