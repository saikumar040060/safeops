import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import ApprovalRequest
from app.schemas.approval_request import ApprovalRequestRead
from app.services.approval_engine import ApprovalActionResult, ApprovalEngine

router = APIRouter(prefix="/approvals", tags=["approvals"])
approval_engine = ApprovalEngine()


class ApproveRequestBody(BaseModel):
    resolved_by: str


class RejectRequestBody(BaseModel):
    resolved_by: str
    reason: str | None = None


@router.get("", response_model=list[ApprovalRequestRead])
def list_approvals(db: Session = Depends(get_db)) -> list[ApprovalRequest]:
    return list(db.scalars(select(ApprovalRequest).order_by(ApprovalRequest.requested_at.desc())))


@router.get("/{approval_id}", response_model=ApprovalRequestRead)
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
    approval_id: uuid.UUID, body: ApproveRequestBody, db: Session = Depends(get_db)
) -> ApprovalActionResult:
    result = approval_engine.approve(approval_id=approval_id, resolved_by=body.resolved_by, db=db)
    return _result_or_error(result)


@router.post("/{approval_id}/reject", response_model=ApprovalActionResult)
def reject_approval(
    approval_id: uuid.UUID, body: RejectRequestBody, db: Session = Depends(get_db)
) -> ApprovalActionResult:
    result = approval_engine.reject(
        approval_id=approval_id, resolved_by=body.resolved_by, reason=body.reason, db=db
    )
    return _result_or_error(result)
