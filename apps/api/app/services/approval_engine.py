import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import (
    Agent,
    ApprovalRequest,
    AuditEvent,
    Execution,
    ToolRequest,
)
from app.models.enums import ApprovalStatus, AuditEventType, ExecutionStatus, ToolRequestStatus
from app.services.audit import commit_chunk
from app.tools import ToolNotFoundError, tool_registry

APPROVAL_EXPIRY = timedelta(minutes=15)


class ApprovalActionResult(BaseModel):
    status: str
    approval_id: str | None = None
    approval_status: str | None = None
    tool_result: dict[str, Any] | None = None
    reason: str | None = None


class ApprovalEngine:
    def create_approval(
        self,
        *,
        approval_id: uuid.UUID,
        execution_id: uuid.UUID,
        agent_id: uuid.UUID,
        tool_request_id: uuid.UUID,
        policy_decision_id: uuid.UUID,
        tool_name: str,
        arguments: dict[str, Any],
        risk_level: Any,
        reason: str,
    ) -> ApprovalRequest:
        now = datetime.now(UTC)
        return ApprovalRequest(
            id=approval_id,
            execution_id=execution_id,
            agent_id=agent_id,
            tool_request_id=tool_request_id,
            policy_decision_id=policy_decision_id,
            tool_name=tool_name,
            approved_arguments=arguments,
            risk_level=risk_level,
            reason=reason,
            status=ApprovalStatus.PENDING,
            expires_at=now + APPROVAL_EXPIRY,
        )

    def get(self, approval_id: uuid.UUID, db: Session) -> ApprovalRequest | None:
        return db.get(ApprovalRequest, approval_id)

    def approve(
        self, *, approval_id: uuid.UUID, resolved_by: str, db: Session
    ) -> ApprovalActionResult:
        return self._resolve(
            approval_id=approval_id, resolved_by=resolved_by, approve=True, db=db
        )

    def reject(
        self, *, approval_id: uuid.UUID, resolved_by: str, reason: str | None, db: Session
    ) -> ApprovalActionResult:
        return self._resolve(
            approval_id=approval_id,
            resolved_by=resolved_by,
            approve=False,
            rejection_reason=reason,
            db=db,
        )

    def _resolve(
        self,
        *,
        approval_id: uuid.UUID,
        resolved_by: str,
        approve: bool,
        db: Session,
        rejection_reason: str | None = None,
    ) -> ApprovalActionResult:
        approval = db.get(ApprovalRequest, approval_id)
        if approval is None:
            return ApprovalActionResult(status="NOT_FOUND", reason="Approval request not found")

        now = datetime.now(UTC)
        self._lazy_expire(approval, now, db)

        if approval.status != ApprovalStatus.PENDING:
            return ApprovalActionResult(
                status="ALREADY_RESOLVED",
                approval_id=str(approval.id),
                approval_status=approval.status.value,
                reason=f"Approval request is already {approval.status.value}",
            )

        tool_request = db.get(ToolRequest, approval.tool_request_id)
        execution = db.get(Execution, approval.execution_id)
        if (
            tool_request is None
            or tool_request.status != ToolRequestStatus.REQUIRES_APPROVAL
            or execution is None
            or execution.status != ExecutionStatus.WAITING_APPROVAL
            or tool_request.execution_id != approval.execution_id
        ):
            return ApprovalActionResult(
                status="INVALID_STATE",
                approval_id=str(approval.id),
                reason="Execution or tool request is not in an approvable state",
            )

        new_status = ApprovalStatus.APPROVED if approve else ApprovalStatus.REJECTED
        claimed = (
            db.execute(
                update(ApprovalRequest)
                .where(
                    ApprovalRequest.id == approval.id,
                    ApprovalRequest.status == ApprovalStatus.PENDING,
                    ApprovalRequest.expires_at > now,
                )
                .values(status=new_status, resolved_at=now, resolved_by=resolved_by)
            ).rowcount
            > 0
        )
        db.commit()
        db.refresh(approval)

        if not claimed:
            return ApprovalActionResult(
                status="ALREADY_RESOLVED",
                approval_id=str(approval.id),
                approval_status=approval.status.value,
                reason=f"Approval request is already {approval.status.value}",
            )

        agent = db.get(Agent, approval.agent_id)

        if not approve:
            tool_request.status = ToolRequestStatus.DENIED
            tool_request.completed_at = now
            tool_request.error = {
                "code": "APPROVAL_REJECTED",
                "message": rejection_reason or "Rejected by approver",
            }
            execution.status = ExecutionStatus.RUNNING
            commit_chunk(
                db,
                execution.id,
                lambda seq: [
                    AuditEvent(
                        execution_id=execution.id,
                        sequence=seq,
                        event_type=AuditEventType.APPROVAL_REJECTED,
                        actor=resolved_by,
                        event_metadata={
                            "approval_id": str(approval.id),
                            "tool_name": approval.tool_name,
                        },
                    ),
                    tool_request,
                ],
            )
            return ApprovalActionResult(
                status="REJECTED", approval_id=str(approval.id), approval_status="REJECTED"
            )

        commit_chunk(
            db,
            execution.id,
            lambda seq: [
                AuditEvent(
                    execution_id=execution.id,
                    sequence=seq,
                    event_type=AuditEventType.APPROVAL_APPROVED,
                    actor=resolved_by,
                    event_metadata={
                        "approval_id": str(approval.id),
                        "tool_name": approval.tool_name,
                    },
                )
            ],
        )

        return self._execute_approved_action(
            approval=approval,
            tool_request=tool_request,
            execution=execution,
            agent_name=agent.name if agent else "unknown-agent",
            db=db,
        )

    def _execute_approved_action(
        self,
        *,
        approval: ApprovalRequest,
        tool_request: ToolRequest,
        execution: Execution,
        agent_name: str,
        db: Session,
    ) -> ApprovalActionResult:
        commit_chunk(
            db,
            execution.id,
            lambda seq: [
                AuditEvent(
                    execution_id=execution.id,
                    sequence=seq,
                    event_type=AuditEventType.APPROVED_ACTION_EXECUTION_STARTED,
                    actor=agent_name,
                    event_metadata={"tool_name": approval.tool_name},
                )
            ],
        )

        try:
            tool = tool_registry.get(approval.tool_name)
        except ToolNotFoundError:
            return self._finalize_execution_outcome(
                approval=approval,
                tool_request=tool_request,
                execution=execution,
                agent_name=agent_name,
                success=False,
                error={
                    "code": "TOOL_NOT_FOUND",
                    "message": "Approved tool is no longer registered",
                },
                result=None,
                db=db,
            )

        try:
            result = tool.execute(approval.approved_arguments, db)
        except Exception:
            db.rollback()
            error = {
                "code": "TOOL_EXECUTION_ERROR",
                "message": "Tool execution raised an unexpected error",
            }
            return self._finalize_execution_outcome(
                approval=approval,
                tool_request=tool_request,
                execution=execution,
                agent_name=agent_name,
                success=False,
                error=error,
                result=None,
                db=db,
            )

        if result.success:
            return self._finalize_execution_outcome(
                approval=approval,
                tool_request=tool_request,
                execution=execution,
                agent_name=agent_name,
                success=True,
                error=None,
                result=result.data,
                db=db,
            )

        error = result.error.model_dump() if result.error else {"code": "UNKNOWN", "message": ""}
        return self._finalize_execution_outcome(
            approval=approval,
            tool_request=tool_request,
            execution=execution,
            agent_name=agent_name,
            success=False,
            error=error,
            result=None,
            db=db,
        )

    def _finalize_execution_outcome(
        self,
        *,
        approval: ApprovalRequest,
        tool_request: ToolRequest,
        execution: Execution,
        agent_name: str,
        success: bool,
        error: dict[str, Any] | None,
        result: dict[str, Any] | None,
        db: Session,
    ) -> ApprovalActionResult:
        now = datetime.now(UTC)
        approval.status = ApprovalStatus.EXECUTED
        approval.executed_at = now
        tool_request.status = ToolRequestStatus.EXECUTED if success else ToolRequestStatus.FAILED
        tool_request.completed_at = now
        tool_request.result = result
        tool_request.error = error
        execution.status = ExecutionStatus.RUNNING

        event_type = (
            AuditEventType.APPROVED_ACTION_EXECUTED
            if success
            else AuditEventType.APPROVED_ACTION_FAILED
        )
        commit_chunk(
            db,
            execution.id,
            lambda seq: [
                AuditEvent(
                    execution_id=execution.id,
                    sequence=seq,
                    event_type=event_type,
                    actor=agent_name,
                    event_metadata={"tool_name": approval.tool_name, "error": error}
                    if error
                    else {"tool_name": approval.tool_name},
                ),
                approval,
                tool_request,
            ],
        )

        return ApprovalActionResult(
            status="EXECUTED" if success else "FAILED",
            approval_id=str(approval.id),
            approval_status="EXECUTED",
            tool_result=result,
            reason=error.get("message") if error else None,
        )

    @staticmethod
    def _lazy_expire(approval: ApprovalRequest, now: datetime, db: Session) -> None:
        if approval.status != ApprovalStatus.PENDING or approval.expires_at > now:
            return
        expired = (
            db.execute(
                update(ApprovalRequest)
                .where(
                    ApprovalRequest.id == approval.id,
                    ApprovalRequest.status == ApprovalStatus.PENDING,
                )
                .values(status=ApprovalStatus.EXPIRED, resolved_at=now)
            ).rowcount
            > 0
        )
        db.commit()
        db.refresh(approval)
        if expired:
            commit_chunk(
                db,
                approval.execution_id,
                lambda seq: [
                    AuditEvent(
                        execution_id=approval.execution_id,
                        sequence=seq,
                        event_type=AuditEventType.APPROVAL_EXPIRED,
                        actor="system",
                        event_metadata={
                            "approval_id": str(approval.id),
                            "tool_name": approval.tool_name,
                        },
                    )
                ],
            )
