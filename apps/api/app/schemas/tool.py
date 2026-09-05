import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import RiskLevel


class ToolRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    risk_category: RiskLevel
    enabled: bool
    created_at: datetime
    updated_at: datetime
