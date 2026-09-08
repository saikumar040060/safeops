import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import AgentStatus, PermissionType, RiskLevel


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


class ToolPermissionSummary(BaseModel):
    tool_id: uuid.UUID
    tool_name: str
    permission: PermissionType
    risk_category: RiskLevel


class ExecutionBrief(BaseModel):
    id: uuid.UUID
    objective: str
    status: str
    created_at: datetime
    completed_at: datetime | None


class AgentDetail(AgentRead):
    permissions: list[ToolPermissionSummary]
    recent_executions: list[ExecutionBrief]
