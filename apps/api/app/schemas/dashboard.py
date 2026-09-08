from pydantic import BaseModel

from app.schemas.approval_request import ApprovalRequestRead
from app.schemas.audit_event import AuditEventRead
from app.schemas.execution import ExecutionRead
from app.schemas.security_incident import SecurityIncidentRead


class SeverityCount(BaseModel):
    severity: str
    count: int


class DashboardMetrics(BaseModel):
    active_executions: int
    waiting_approvals: int
    blocked_actions: int
    open_security_incidents: int
    completed_executions: int
    risk_assessments_by_severity: list[SeverityCount]


class DashboardSummary(BaseModel):
    metrics: DashboardMetrics
    recent_executions: list[ExecutionRead]
    recent_approvals: list[ApprovalRequestRead]
    recent_incidents: list[SecurityIncidentRead]
    recent_blocked: list[AuditEventRead]
