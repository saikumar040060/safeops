from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.metrics import snapshot_latency
from app.core.security import require_permission
from app.models import ApprovalRequest, AuditEvent, Execution, SecurityIncident, ToolRequest
from app.models.enums import (
    ApprovalStatus,
    AuditEventType,
    ExecutionStatus,
    IncidentStatus,
    ToolRequestStatus,
)

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("", dependencies=[Depends(require_permission("read"))])
def get_metrics(db: Session = Depends(get_db)) -> dict:
    """Safe operational counters derived from durable state -- never
    exposes tool arguments, ticket content, or any other label with
    potentially sensitive data, only counts and latency. Requires
    authentication like every other read endpoint; in production this
    should additionally be bound to an internal network / scrape target
    rather than exposed publicly (see infra/docker notes)."""

    def count(*where) -> int:
        query = select(func.count()).select_from(Execution)
        if where:
            query = query.where(*where)
        return db.scalar(query) or 0

    executions_started_total = (
        db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.event_type == AuditEventType.EXECUTION_STARTED)
        )
        or 0
    )
    executions_blocked_total = count(Execution.status == ExecutionStatus.BLOCKED)
    approvals_pending = (
        db.scalar(
            select(func.count())
            .select_from(ApprovalRequest)
            .where(ApprovalRequest.status == ApprovalStatus.PENDING)
        )
        or 0
    )
    risk_blocks_total = (
        db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.event_type == AuditEventType.ACTION_BLOCKED_BY_RISK)
        )
        or 0
    )
    security_incidents_open = (
        db.scalar(
            select(func.count())
            .select_from(SecurityIncident)
            .where(SecurityIncident.status == IncidentStatus.OPEN)
        )
        or 0
    )
    tool_failures_total = (
        db.scalar(
            select(func.count())
            .select_from(ToolRequest)
            .where(ToolRequest.status == ToolRequestStatus.FAILED)
        )
        or 0
    )

    return {
        "executions_started_total": executions_started_total,
        "executions_blocked_total": executions_blocked_total,
        "approvals_pending": approvals_pending,
        "risk_blocks_total": risk_blocks_total,
        "security_incidents_open": security_incidents_open,
        "tool_failures_total": tool_failures_total,
        "request_latency": snapshot_latency(),
    }
