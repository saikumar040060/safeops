import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_permission
from app.models import AuditEvent, Execution
from app.models.enums import AuditEventType
from app.schemas.audit_event import AuditEventRead

router = APIRouter(
    prefix="/audit", tags=["audit"], dependencies=[Depends(require_permission("read"))]
)


@router.get("", response_model=list[AuditEventRead])
def list_audit_events(
    execution_id: uuid.UUID | None = Query(default=None),
    agent_id: uuid.UUID | None = Query(default=None),
    event_type: AuditEventType | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[AuditEvent]:
    query = select(AuditEvent)
    if execution_id is not None:
        query = query.where(AuditEvent.execution_id == execution_id)
    if agent_id is not None:
        query = query.where(
            AuditEvent.execution_id.in_(select(Execution.id).where(Execution.agent_id == agent_id))
        )
    if event_type is not None:
        query = query.where(AuditEvent.event_type == event_type)
    query = query.order_by(AuditEvent.timestamp.desc()).limit(limit).offset(offset)
    return list(db.scalars(query))


@router.get("/executions/{execution_id}", response_model=list[AuditEventRead])
def list_execution_audit_events(
    execution_id: uuid.UUID, db: Session = Depends(get_db)
) -> list[AuditEvent]:
    # Sequence, not timestamp, is the authoritative ordering within one
    # execution -- it is assigned atomically by commit_chunk and can never
    # collide or go out of order, unlike wall-clock timestamps.
    return list(
        db.scalars(
            select(AuditEvent)
            .where(AuditEvent.execution_id == execution_id)
            .order_by(AuditEvent.sequence)
        )
    )
