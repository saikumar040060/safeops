import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.security import require_permission
from app.models import AuditEvent, Execution, ExecutionStep, Operator, RiskAssessment
from app.models.enums import ExecutionStatus, StepType
from app.schemas.execution import (
    ExecutionRead,
    ExecutionStepRead,
    ExecutionSummary,
    ExecutionTimeline,
)
from app.services.agent_runtime import AgentRuntime, RuntimeResult

router = APIRouter(prefix="/executions", tags=["executions"])
runtime = AgentRuntime()

_read = Depends(require_permission("read"))
_execute = Depends(require_permission("execute"))


class StartExecutionBody(BaseModel):
    agent_id: uuid.UUID
    objective: str
    context: dict[str, Any] | None = None


_NOT_FOUND_STATUSES = {"NOT_FOUND"}


def _result_or_404(result: RuntimeResult) -> RuntimeResult:
    if result.status in _NOT_FOUND_STATUSES:
        raise HTTPException(status_code=404, detail=result.model_dump())
    return result


@router.post("", response_model=RuntimeResult)
def create_execution(
    body: StartExecutionBody,
    db: Session = Depends(get_db),
    operator: Operator = _execute,
) -> RuntimeResult:
    rate_limit("execution_create", operator.id, max_requests=20, window_seconds=60)
    result = runtime.start_execution(
        agent_id=body.agent_id, objective=body.objective, context=body.context, db=db
    )
    return _result_or_404(result)


@router.get("", response_model=list[ExecutionSummary], dependencies=[_read])
def list_executions(
    status: ExecutionStatus | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[ExecutionSummary]:
    query = select(Execution)
    if status is not None:
        query = query.where(Execution.status == status)
    query = query.order_by(Execution.created_at.desc()).limit(limit).offset(offset)
    executions = list(db.scalars(query))
    return _to_summaries(db, executions)


@router.get("/{execution_id}", response_model=ExecutionRead, dependencies=[_read])
def get_execution(execution_id: uuid.UUID, db: Session = Depends(get_db)) -> Execution:
    execution = db.get(Execution, execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="Execution not found")
    return execution


@router.get("/{execution_id}/steps", response_model=list[ExecutionStepRead], dependencies=[_read])
def list_execution_steps(
    execution_id: uuid.UUID, db: Session = Depends(get_db)
) -> list[ExecutionStep]:
    return list(
        db.scalars(
            select(ExecutionStep)
            .where(ExecutionStep.execution_id == execution_id)
            .order_by(ExecutionStep.sequence)
        )
    )


@router.get("/{execution_id}/timeline", response_model=ExecutionTimeline, dependencies=[_read])
def get_execution_timeline(
    execution_id: uuid.UUID, db: Session = Depends(get_db)
) -> ExecutionTimeline:
    execution = db.get(Execution, execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="Execution not found")

    steps = list(
        db.scalars(
            select(ExecutionStep)
            .where(ExecutionStep.execution_id == execution_id)
            .order_by(ExecutionStep.sequence)
        )
    )
    # Sequence is the authoritative ordering within an execution (assigned
    # atomically by commit_chunk); never re-sort audit events by timestamp.
    audit_events = list(
        db.scalars(
            select(AuditEvent)
            .where(AuditEvent.execution_id == execution_id)
            .order_by(AuditEvent.sequence)
        )
    )
    return ExecutionTimeline(execution=execution, steps=steps, audit_events=audit_events)


def _to_summaries(db: Session, executions: list[Execution]) -> list[ExecutionSummary]:
    execution_ids = [execution.id for execution in executions]
    if not execution_ids:
        return []

    latest_step_by_execution: dict[uuid.UUID, ExecutionStep] = {}
    for step in db.scalars(
        select(ExecutionStep)
        .where(ExecutionStep.execution_id.in_(execution_ids))
        .order_by(ExecutionStep.execution_id, ExecutionStep.sequence.desc())
    ):
        latest_step_by_execution.setdefault(step.execution_id, step)

    latest_risk_by_execution: dict[uuid.UUID, RiskAssessment] = {}
    for assessment in db.scalars(
        select(RiskAssessment)
        .where(RiskAssessment.execution_id.in_(execution_ids))
        .order_by(RiskAssessment.execution_id, RiskAssessment.created_at.desc())
    ):
        latest_risk_by_execution.setdefault(assessment.execution_id, assessment)

    summaries = []
    for execution in executions:
        step = latest_step_by_execution.get(execution.id)
        current_step = None
        if step is not None:
            if step.step_type == StepType.FINAL:
                current_step = (step.input or {}).get("decision", step.step_type.value)
            else:
                current_step = (step.input or {}).get("tool_name", step.step_type.value)
        risk = latest_risk_by_execution.get(execution.id)
        updated_at = execution.completed_at or execution.created_at
        if step is not None:
            updated_at = step.completed_at or step.created_at
        summaries.append(
            ExecutionSummary(
                id=execution.id,
                agent_id=execution.agent_id,
                objective=execution.objective,
                status=execution.status,
                initial_context=execution.initial_context,
                created_at=execution.created_at,
                started_at=execution.started_at,
                completed_at=execution.completed_at,
                current_step=current_step,
                latest_risk_level=risk.risk_level.value if risk else None,
                updated_at=updated_at,
            )
        )
    return summaries


@router.post("/{execution_id}/step", response_model=RuntimeResult)
def step_execution(
    execution_id: uuid.UUID, db: Session = Depends(get_db), operator: Operator = _execute
) -> RuntimeResult:
    rate_limit("execution_step", operator.id, max_requests=120, window_seconds=60)
    return _result_or_404(runtime.step(execution_id, db))


@router.post("/{execution_id}/resume", response_model=RuntimeResult)
def resume_execution(
    execution_id: uuid.UUID, db: Session = Depends(get_db), operator: Operator = _execute
) -> RuntimeResult:
    rate_limit("execution_resume", operator.id, max_requests=120, window_seconds=60)
    return _result_or_404(runtime.resume(execution_id, db))


@router.post("/{execution_id}/cancel", response_model=RuntimeResult)
def cancel_execution(
    execution_id: uuid.UUID, db: Session = Depends(get_db), operator: Operator = _execute
) -> RuntimeResult:
    return _result_or_404(runtime.cancel(execution_id, db))
