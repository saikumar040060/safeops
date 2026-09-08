from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import ApprovalRequest, AuditEvent, Execution, RiskAssessment, SecurityIncident
from app.models.enums import ApprovalStatus, AuditEventType, ExecutionStatus, IncidentStatus
from app.schemas.dashboard import DashboardMetrics, DashboardSummary, SeverityCount

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

BLOCKED_EVENT_TYPES = (
    AuditEventType.ACTION_DENIED,
    AuditEventType.ACTION_BLOCKED,
    AuditEventType.ACTION_BLOCKED_BY_RISK,
    AuditEventType.POLICY_BLOCKED,
    AuditEventType.EXECUTION_BLOCKED,
)


@router.get("/summary", response_model=DashboardSummary)
def get_dashboard_summary(db: Session = Depends(get_db)) -> DashboardSummary:
    active_executions = db.scalar(
        select(func.count())
        .select_from(Execution)
        .where(
            Execution.status.in_([ExecutionStatus.RUNNING, ExecutionStatus.WAITING_APPROVAL])
        )
    )
    waiting_approvals = db.scalar(
        select(func.count())
        .select_from(ApprovalRequest)
        .where(ApprovalRequest.status == ApprovalStatus.PENDING)
    )
    blocked_actions = db.scalar(
        select(func.count())
        .select_from(Execution)
        .where(Execution.status == ExecutionStatus.BLOCKED)
    )
    open_security_incidents = db.scalar(
        select(func.count())
        .select_from(SecurityIncident)
        .where(SecurityIncident.status == IncidentStatus.OPEN)
    )
    completed_executions = db.scalar(
        select(func.count())
        .select_from(Execution)
        .where(Execution.status == ExecutionStatus.COMPLETED)
    )

    severity_rows = db.execute(
        select(RiskAssessment.risk_level, func.count())
        .group_by(RiskAssessment.risk_level)
        .order_by(RiskAssessment.risk_level)
    ).all()
    risk_by_severity = [
        SeverityCount(severity=level.value, count=count) for level, count in severity_rows
    ]

    recent_executions = list(
        db.scalars(select(Execution).order_by(Execution.created_at.desc()).limit(5))
    )
    recent_approvals = list(
        db.scalars(select(ApprovalRequest).order_by(ApprovalRequest.requested_at.desc()).limit(5))
    )
    recent_incidents = list(
        db.scalars(select(SecurityIncident).order_by(SecurityIncident.created_at.desc()).limit(5))
    )
    recent_blocked = list(
        db.scalars(
            select(AuditEvent)
            .where(AuditEvent.event_type.in_(BLOCKED_EVENT_TYPES))
            .order_by(AuditEvent.timestamp.desc())
            .limit(5)
        )
    )

    return DashboardSummary(
        metrics=DashboardMetrics(
            active_executions=active_executions or 0,
            waiting_approvals=waiting_approvals or 0,
            blocked_actions=blocked_actions or 0,
            open_security_incidents=open_security_incidents or 0,
            completed_executions=completed_executions or 0,
            risk_assessments_by_severity=risk_by_severity,
        ),
        recent_executions=recent_executions,
        recent_approvals=recent_approvals,
        recent_incidents=recent_incidents,
        recent_blocked=recent_blocked,
    )
