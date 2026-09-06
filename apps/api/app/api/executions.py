import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Execution, ExecutionStep
from app.schemas.execution import ExecutionRead, ExecutionStepRead
from app.services.agent_runtime import AgentRuntime, RuntimeResult

router = APIRouter(prefix="/executions", tags=["executions"])
runtime = AgentRuntime()


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
def create_execution(body: StartExecutionBody, db: Session = Depends(get_db)) -> RuntimeResult:
    result = runtime.start_execution(
        agent_id=body.agent_id, objective=body.objective, context=body.context, db=db
    )
    return _result_or_404(result)


@router.get("", response_model=list[ExecutionRead])
def list_executions(db: Session = Depends(get_db)) -> list[Execution]:
    return list(db.scalars(select(Execution).order_by(Execution.created_at.desc())))


@router.get("/{execution_id}", response_model=ExecutionRead)
def get_execution(execution_id: uuid.UUID, db: Session = Depends(get_db)) -> Execution:
    execution = db.get(Execution, execution_id)
    if execution is None:
        raise HTTPException(status_code=404, detail="Execution not found")
    return execution


@router.get("/{execution_id}/steps", response_model=list[ExecutionStepRead])
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


@router.post("/{execution_id}/step", response_model=RuntimeResult)
def step_execution(execution_id: uuid.UUID, db: Session = Depends(get_db)) -> RuntimeResult:
    return _result_or_404(runtime.step(execution_id, db))


@router.post("/{execution_id}/resume", response_model=RuntimeResult)
def resume_execution(execution_id: uuid.UUID, db: Session = Depends(get_db)) -> RuntimeResult:
    return _result_or_404(runtime.resume(execution_id, db))


@router.post("/{execution_id}/cancel", response_model=RuntimeResult)
def cancel_execution(execution_id: uuid.UUID, db: Session = Depends(get_db)) -> RuntimeResult:
    return _result_or_404(runtime.cancel(execution_id, db))
