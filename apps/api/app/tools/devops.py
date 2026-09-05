from datetime import datetime

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Deployment, Service, ServiceLog
from app.models.enums import DeploymentEnvironment
from app.tools.base import BaseTool, ToolExecutionError


def _get_service(service_name: str, db: Session) -> Service:
    service = db.scalar(select(Service).where(Service.name == service_name))
    if service is None:
        raise ToolExecutionError("NOT_FOUND", f"Service '{service_name}' not found")
    return service


def _latest_deployment(
    service: Service, environment: DeploymentEnvironment, db: Session
) -> Deployment | None:
    return db.scalar(
        select(Deployment)
        .where(Deployment.service_id == service.id, Deployment.environment == environment)
        .order_by(Deployment.deployed_at.desc(), Deployment.id.desc())
        .limit(1)
    )


class ReadLogsInput(BaseModel):
    service_name: str
    limit: int = Field(default=50, gt=0, le=500)


class LogEntry(BaseModel):
    level: str
    message: str
    timestamp: datetime


class ReadLogsOutput(BaseModel):
    service_name: str
    logs: list[LogEntry]


class ReadLogsTool(BaseTool):
    name = "read_logs"
    description = "Read service logs."
    input_schema = ReadLogsInput
    output_schema = ReadLogsOutput

    def _run(self, input: ReadLogsInput, db: Session) -> ReadLogsOutput:
        service = _get_service(input.service_name, db)
        logs = db.scalars(
            select(ServiceLog)
            .where(ServiceLog.service_id == service.id)
            .order_by(ServiceLog.timestamp.desc())
            .limit(input.limit)
        ).all()
        return ReadLogsOutput(
            service_name=service.name,
            logs=[
                LogEntry(level=log.level.value, message=log.message, timestamp=log.timestamp)
                for log in logs
            ],
        )


class GetDeploymentInput(BaseModel):
    service_name: str


class DeploymentState(BaseModel):
    version: str
    deployed_at: datetime


class GetDeploymentOutput(BaseModel):
    service_name: str
    staging: DeploymentState | None
    production: DeploymentState | None


class GetDeploymentTool(BaseTool):
    name = "get_deployment"
    description = "Read current deployment status for a service."
    input_schema = GetDeploymentInput
    output_schema = GetDeploymentOutput

    def _run(self, input: GetDeploymentInput, db: Session) -> GetDeploymentOutput:
        service = _get_service(input.service_name, db)
        staging = _latest_deployment(service, DeploymentEnvironment.STAGING, db)
        production = _latest_deployment(service, DeploymentEnvironment.PRODUCTION, db)
        return GetDeploymentOutput(
            service_name=service.name,
            staging=DeploymentState(version=staging.version, deployed_at=staging.deployed_at)
            if staging
            else None,
            production=DeploymentState(
                version=production.version, deployed_at=production.deployed_at
            )
            if production
            else None,
        )


class DeployInput(BaseModel):
    service_name: str
    version: str


class DeployOutput(BaseModel):
    service_name: str
    environment: str
    version: str
    deployed_at: datetime


def _deploy(
    input: DeployInput, db: Session, environment: DeploymentEnvironment
) -> DeployOutput:
    service = _get_service(input.service_name, db)
    deployment = Deployment(service_id=service.id, environment=environment, version=input.version)
    db.add(deployment)
    db.commit()
    db.refresh(deployment)
    return DeployOutput(
        service_name=service.name,
        environment=deployment.environment.value,
        version=deployment.version,
        deployed_at=deployment.deployed_at,
    )


class DeployStagingTool(BaseTool):
    name = "deploy_staging"
    description = "Deploy a build to the staging environment."
    input_schema = DeployInput
    output_schema = DeployOutput

    def _run(self, input: DeployInput, db: Session) -> DeployOutput:
        return _deploy(input, db, DeploymentEnvironment.STAGING)


class DeployProductionTool(BaseTool):
    name = "deploy_production"
    description = "Deploy a build to the production environment."
    input_schema = DeployInput
    output_schema = DeployOutput

    def _run(self, input: DeployInput, db: Session) -> DeployOutput:
        return _deploy(input, db, DeploymentEnvironment.PRODUCTION)
