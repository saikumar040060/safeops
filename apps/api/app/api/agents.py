import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import Agent, AgentToolPermission, Execution, Tool
from app.schemas.agent import AgentDetail, AgentRead, ExecutionBrief, ToolPermissionSummary

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=list[AgentRead])
def list_agents(db: Session = Depends(get_db)) -> list[Agent]:
    return list(db.scalars(select(Agent).order_by(Agent.name)))


@router.get("/{agent_id}", response_model=AgentDetail)
def get_agent(agent_id: uuid.UUID, db: Session = Depends(get_db)) -> AgentDetail:
    agent = db.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    permission_rows = db.execute(
        select(AgentToolPermission, Tool)
        .join(Tool, Tool.id == AgentToolPermission.tool_id)
        .where(AgentToolPermission.agent_id == agent_id)
        .order_by(Tool.name)
    ).all()
    permissions = [
        ToolPermissionSummary(
            tool_id=tool.id,
            tool_name=tool.name,
            permission=permission.permission,
            risk_category=tool.risk_category,
        )
        for permission, tool in permission_rows
    ]

    recent_executions = list(
        db.scalars(
            select(Execution)
            .where(Execution.agent_id == agent_id)
            .order_by(Execution.created_at.desc())
            .limit(10)
        )
    )

    return AgentDetail(
        id=agent.id,
        name=agent.name,
        type=agent.type,
        description=agent.description,
        status=agent.status,
        risk_level=agent.risk_level,
        created_at=agent.created_at,
        updated_at=agent.updated_at,
        permissions=permissions,
        recent_executions=[
            ExecutionBrief(
                id=execution.id,
                objective=execution.objective,
                status=execution.status.value,
                created_at=execution.created_at,
                completed_at=execution.completed_at,
            )
            for execution in recent_executions
        ],
    )
