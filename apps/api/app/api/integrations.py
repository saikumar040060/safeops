import uuid
from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.security import require_scope
from app.models import Operator
from app.schemas.external_action import (
    ActionResponse,
    ActionStatusResponse,
    SubmitActionRequest,
    ToolDescriptor,
)
from app.services.external_action_service import ExternalActionError, ExternalActionService

router = APIRouter(prefix="/integrations", tags=["integrations"])
service = ExternalActionService()


def _raise(exc: ExternalActionError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}
    )


@router.post("/actions", response_model=ActionResponse)
def submit_action(
    body: SubmitActionRequest,
    db: Session = Depends(get_db),
    operator: Operator = Depends(require_scope("actions:submit")),
) -> ActionResponse:
    rate_limit("integration_action_submit", operator.id, max_requests=30, window_seconds=60)
    try:
        return service.submit(operator=operator, request=body, db=db)
    except ExternalActionError as exc:
        _raise(exc)


@router.get("/actions/{external_request_id}", response_model=ActionStatusResponse)
def get_action(
    external_request_id: str,
    db: Session = Depends(get_db),
    operator: Operator = Depends(require_scope("actions:read")),
) -> ActionStatusResponse:
    rate_limit("integration_action_read", operator.id, max_requests=120, window_seconds=60)
    try:
        return service.get_status(operator=operator, external_request_id=external_request_id, db=db)
    except ExternalActionError as exc:
        _raise(exc)


@router.get("/tools", response_model=list[ToolDescriptor])
def list_tools(
    safeops_agent_id: uuid.UUID,
    db: Session = Depends(get_db),
    operator: Operator = Depends(require_scope("actions:read")),
) -> list[ToolDescriptor]:
    rate_limit("integration_tools_list", operator.id, max_requests=60, window_seconds=60)
    try:
        return service.list_tools(operator=operator, safeops_agent_id=safeops_agent_id, db=db)
    except ExternalActionError as exc:
        _raise(exc)
