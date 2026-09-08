import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import SecurityIncident
from app.models.enums import IncidentStatus, RiskLevel
from app.schemas.security_incident import SecurityIncidentRead

router = APIRouter(prefix="/security", tags=["security"])


@router.get("/incidents", response_model=list[SecurityIncidentRead])
def list_security_incidents(
    severity: RiskLevel | None = Query(default=None),
    status: IncidentStatus | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[SecurityIncident]:
    query = select(SecurityIncident)
    if severity is not None:
        query = query.where(SecurityIncident.severity == severity)
    if status is not None:
        query = query.where(SecurityIncident.status == status)
    query = query.order_by(SecurityIncident.created_at.desc()).limit(limit).offset(offset)
    return list(db.scalars(query))


@router.get("/incidents/{incident_id}", response_model=SecurityIncidentRead)
def get_security_incident(
    incident_id: uuid.UUID, db: Session = Depends(get_db)
) -> SecurityIncident:
    incident = db.get(SecurityIncident, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="Security incident not found")
    return incident
