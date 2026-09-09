import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.security import require_permission
from app.models import ApprovalRequest, Operator
from app.schemas.approval_request import ApprovalRequestRead
from app.services.approval_engine import ApprovalActionResult, ApprovalEngine

router = APIRouter(prefix="/approvals", tags=["approvals"])
approval_engine = ApprovalEngine()

_read = Depends(require_permission("read"))
_approve = Depends(require_permission("approve"))


class ApproveRequestBody(BaseModel):
    """Deliberately carries no resolver identity field. Approver identity
    always comes from the authenticated Operator resolved from the bearer
    token -- a caller cannot override it, so this model has nothing left to
    accept there. Any extra JSON fields a client sends (e.g. a leftover
    `resolved_by`) are silently ignored by Pydantic's default `extra`
    behavior rather than rejected, so an old client body is harmless."""


class RejectRequestBody(BaseModel):
    reason: str | None = None


@router.get("", response_model=list[ApprovalRequestRead], dependencies=[_read])
def list_approvals(db: Session = Depends(get_db)) -> list[ApprovalRequest]:
    return list(db.scalars(select(ApprovalRequest).order_by(ApprovalRequest.requested_at.desc())))


@router.get("/{approval_id}", response_model=ApprovalRequestRead, dependencies=[_read])
def get_approval(approval_id: uuid.UUID, db: Session = Depends(get_db)) -> ApprovalRequest:
    approval = approval_engine.get(approval_id, db)
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval request not found")
    return approval


_ERROR_STATUS_CODES = {
    "NOT_FOUND": 404,
    "ALREADY_RESOLVED": 409,
    "INVALID_STATE": 409,
}


def _result_or_error(result: ApprovalActionResult) -> ApprovalActionResult:
    status_code = _ERROR_STATUS_CODES.get(result.status)
    if status_code is not None:
        raise HTTPException(status_code=status_code, detail=result.model_dump())
    return result


@router.post("/{approval_id}/approve", response_model=ApprovalActionResult)
def approve_approval(
    approval_id: uuid.UUID,
    body: ApproveRequestBody,
    db: Session = Depends(get_db),
    operator: Operator = _approve,
) -> ApprovalActionResult:
    rate_limit("approval_resolve", operator.id, max_requests=30, window_seconds=60)
    result = approval_engine.approve(approval_id=approval_id, operator=operator, db=db)
    return _result_or_error(result)


@router.post("/{approval_id}/reject", response_model=ApprovalActionResult)
def reject_approval(
    approval_id: uuid.UUID,
    body: RejectRequestBody,
    db: Session = Depends(get_db),
    operator: Operator = _approve,
) -> ApprovalActionResult:
    rate_limit("approval_resolve", operator.id, max_requests=30, window_seconds=60)
    result = approval_engine.reject(
        approval_id=approval_id, operator=operator, reason=body.reason, db=db
    )
    return _result_or_error(result)
