import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Agent,
    AgentToolPermission,
    AuditEvent,
    Execution,
    PolicyDecision,
    Tool,
    ToolRequest,
)
from app.models.enums import (
    AuditEventType,
    ExecutionStatus,
    PermissionType,
    PolicyAction,
    ToolRequestStatus,
)
from app.services.policy_engine import PolicyEvaluationResult, policy_engine
from app.tools import ToolNotFoundError, tool_registry

NON_EXECUTABLE_STATUSES = {
    ExecutionStatus.COMPLETED,
    ExecutionStatus.FAILED,
    ExecutionStatus.BLOCKED,
}


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


class GatewayResult(BaseModel):
    status: str
    tool_name: str | None = None
    tool_result: dict[str, Any] | None = None
    decision: str | None = None
    reason: str | None = None
    matched_policy: str | None = None
    policy_id: str | None = None


class ToolGateway:
    def execute(
        self,
        *,
        agent_id: uuid.UUID,
        execution_id: uuid.UUID,
        tool_name: str,
        arguments: dict[str, Any],
        db: Session,
    ) -> GatewayResult:
        agent = db.get(Agent, agent_id)
        if agent is None:
            return GatewayResult(status="FAILED", tool_name=tool_name, reason="Agent not found")

        execution = db.get(Execution, execution_id)
        if execution is None:
            return GatewayResult(status="FAILED", tool_name=tool_name, reason="Execution not found")

        if execution.agent_id != agent.id:
            return GatewayResult(
                status="FAILED",
                tool_name=tool_name,
                reason="Execution does not belong to this agent",
            )

        if execution.status in NON_EXECUTABLE_STATUSES:
            return GatewayResult(
                status="FAILED",
                tool_name=tool_name,
                reason=f"Execution is {execution.status.value} and cannot accept new tool calls",
            )

        arguments = _json_safe(arguments)
        safe_args = {"tool_name": tool_name, "arguments": arguments}

        self._commit_chunk(
            db,
            execution.id,
            lambda seq: [
                AuditEvent(
                    execution_id=execution.id,
                    sequence=seq,
                    event_type=AuditEventType.TOOL_REQUESTED,
                    actor=agent.name,
                    event_metadata=safe_args,
                )
            ],
        )

        try:
            tool = tool_registry.get(tool_name)
        except ToolNotFoundError:
            self._commit_chunk(
                db,
                execution.id,
                lambda seq: [
                    AuditEvent(
                        execution_id=execution.id,
                        sequence=seq,
                        event_type=AuditEventType.TOOL_FAILED,
                        actor=agent.name,
                        event_metadata={"reason": "unknown tool"},
                    ),
                    ToolRequest(
                        execution_id=execution.id,
                        agent_id=agent.id,
                        tool_id=None,
                        tool_name=tool_name,
                        arguments=arguments,
                        status=ToolRequestStatus.FAILED,
                        completed_at=datetime.now(UTC),
                        error={"code": "TOOL_NOT_FOUND", "message": f"No tool named '{tool_name}'"},
                    ),
                ],
            )
            return GatewayResult(status="FAILED", tool_name=tool_name, reason="Unknown tool")

        tool_row = db.scalar(select(Tool).where(Tool.name == tool_name))

        try:
            tool.input_schema.model_validate(arguments)
        except ValidationError as exc:
            validation_message = str(exc)
            self._commit_chunk(
                db,
                execution.id,
                lambda seq: [
                    AuditEvent(
                        execution_id=execution.id,
                        sequence=seq,
                        event_type=AuditEventType.TOOL_FAILED,
                        actor=agent.name,
                        event_metadata={"reason": "invalid arguments"},
                    ),
                    ToolRequest(
                        execution_id=execution.id,
                        agent_id=agent.id,
                        tool_id=tool_row.id if tool_row else None,
                        tool_name=tool_name,
                        arguments=arguments,
                        status=ToolRequestStatus.FAILED,
                        completed_at=datetime.now(UTC),
                        error={"code": "INVALID_ARGUMENTS", "message": validation_message},
                    ),
                ],
            )
            return GatewayResult(status="FAILED", tool_name=tool_name, reason="Invalid arguments")

        permission = None
        if tool_row is not None:
            permission = db.scalar(
                select(AgentToolPermission).where(
                    AgentToolPermission.agent_id == agent.id,
                    AgentToolPermission.tool_id == tool_row.id,
                )
            )
        permission_type = permission.permission if permission else PermissionType.DENY

        if permission_type == PermissionType.DENY:
            self._commit_chunk(
                db,
                execution.id,
                lambda seq: [
                    AuditEvent(
                        execution_id=execution.id,
                        sequence=seq,
                        event_type=AuditEventType.PERMISSION_CHECKED,
                        actor=agent.name,
                        event_metadata={"tool_name": tool_name, "permission": "DENY"},
                    ),
                    AuditEvent(
                        execution_id=execution.id,
                        sequence=seq + 1,
                        event_type=AuditEventType.ACTION_DENIED,
                        actor=agent.name,
                        event_metadata={"tool_name": tool_name},
                    ),
                    ToolRequest(
                        execution_id=execution.id,
                        agent_id=agent.id,
                        tool_id=tool_row.id if tool_row else None,
                        tool_name=tool_name,
                        arguments=arguments,
                        status=ToolRequestStatus.DENIED,
                        completed_at=datetime.now(UTC),
                        error={
                            "code": "PERMISSION_DENIED",
                            "message": "Agent does not have permission",
                        },
                    ),
                ],
            )
            return GatewayResult(
                status="BLOCKED",
                tool_name=tool_name,
                decision="DENY",
                reason="Agent does not have permission",
            )

        if permission_type == PermissionType.CONDITIONAL:
            return self._handle_conditional(
                db=db,
                agent=agent,
                execution=execution,
                tool=tool,
                tool_row=tool_row,
                tool_name=tool_name,
                arguments=arguments,
            )

        # ALLOW: record the decision, then execute. The tool owns its own
        # transaction (it may commit/rollback internally, e.g. refund_payment's
        # idempotency retry), so this is a separate commit from what follows.
        self._commit_chunk(
            db,
            execution.id,
            lambda seq: [
                AuditEvent(
                    execution_id=execution.id,
                    sequence=seq,
                    event_type=AuditEventType.PERMISSION_CHECKED,
                    actor=agent.name,
                    event_metadata={"tool_name": tool_name, "permission": "ALLOW"},
                ),
                AuditEvent(
                    execution_id=execution.id,
                    sequence=seq + 1,
                    event_type=AuditEventType.ACTION_ALLOWED,
                    actor=agent.name,
                    event_metadata={"tool_name": tool_name},
                ),
            ],
        )

        tool_request = ToolRequest(
            execution_id=execution.id,
            agent_id=agent.id,
            tool_id=tool_row.id,
            tool_name=tool_name,
            arguments=arguments,
            status=ToolRequestStatus.REQUESTED,
        )
        return self._execute_and_record(
            db=db,
            agent=agent,
            execution=execution,
            tool=tool,
            tool_name=tool_name,
            arguments=arguments,
            tool_request=tool_request,
            decision_label="ALLOW",
        )

    def _handle_conditional(
        self,
        *,
        db: Session,
        agent: Agent,
        execution: Execution,
        tool: Any,
        tool_row: Tool,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> GatewayResult:
        pending_request = ToolRequest(
            execution_id=execution.id,
            agent_id=agent.id,
            tool_id=tool_row.id,
            tool_name=tool_name,
            arguments=arguments,
            status=ToolRequestStatus.REQUESTED,
        )
        self._commit_chunk(
            db,
            execution.id,
            lambda seq: [
                AuditEvent(
                    execution_id=execution.id,
                    sequence=seq,
                    event_type=AuditEventType.PERMISSION_CHECKED,
                    actor=agent.name,
                    event_metadata={"tool_name": tool_name, "permission": "CONDITIONAL"},
                ),
                AuditEvent(
                    execution_id=execution.id,
                    sequence=seq + 1,
                    event_type=AuditEventType.POLICY_EVALUATION_STARTED,
                    actor=agent.name,
                    event_metadata={"tool_name": tool_name},
                ),
                pending_request,
            ],
        )

        # Read-only, deterministic evaluation. No lock is taken on the
        # `policies` table: a concurrent policy edit between this read and
        # our commit below can race, same accepted TOCTOU class as the
        # Milestone 4 permission/execution check.
        try:
            policy_result = policy_engine.evaluate(
                agent=agent, tool=tool_row, arguments=arguments, execution=execution, db=db
            )
        except Exception:
            # Policy evaluation is an authorization boundary. Unexpected
            # evaluator/DB failures must become a generic, persisted BLOCK;
            # never expose exception text and never attempt tool execution.
            db.rollback()
            policy_result = PolicyEvaluationResult(
                decision=PolicyAction.BLOCK,
                reason="POLICY_EVALUATION_ERROR: policy evaluation failed",
                context={
                    "arguments": arguments,
                    "agent": {"id": str(agent.id), "type": agent.type, "name": agent.name},
                    "tool": {"id": str(tool_row.id), "name": tool_row.name},
                    "execution": {"id": str(execution.id)},
                },
            )

        policy_id = str(policy_result.policy_id) if policy_result.policy_id else None

        if policy_result.decision == PolicyAction.ALLOW:
            self._commit_chunk(
                db,
                execution.id,
                self._policy_matched_rows(
                    execution=execution,
                    agent=agent,
                    tool_row=tool_row,
                    tool_name=tool_name,
                    pending_request=pending_request,
                    policy_result=policy_result,
                    terminal_event=AuditEventType.POLICY_ALLOWED,
                ),
            )
            return self._execute_and_record(
                db=db,
                agent=agent,
                execution=execution,
                tool=tool,
                tool_name=tool_name,
                arguments=arguments,
                tool_request=pending_request,
                decision_label="ALLOW",
                matched_policy=policy_result.matched_policy,
                policy_id=policy_id,
            )

        if policy_result.decision == PolicyAction.REQUIRE_APPROVAL:
            pending_request.status = ToolRequestStatus.REQUIRES_APPROVAL
            self._commit_chunk(
                db,
                execution.id,
                self._policy_matched_rows(
                    execution=execution,
                    agent=agent,
                    tool_row=tool_row,
                    tool_name=tool_name,
                    pending_request=pending_request,
                    policy_result=policy_result,
                    terminal_event=AuditEventType.POLICY_APPROVAL_REQUIRED,
                ),
            )
            return GatewayResult(
                status="REQUIRES_APPROVAL",
                tool_name=tool_name,
                decision="REQUIRE_APPROVAL",
                reason=policy_result.reason,
                matched_policy=policy_result.matched_policy,
                policy_id=policy_id,
            )

        # BLOCK (including fail-closed NO_MATCHING_POLICY / POLICY_CONFLICT)
        pending_request.status = ToolRequestStatus.DENIED
        pending_request.completed_at = datetime.now(UTC)
        pending_request.error = {"code": "POLICY_BLOCKED", "message": policy_result.reason}
        self._commit_chunk(
            db,
            execution.id,
            self._policy_matched_rows(
                execution=execution,
                agent=agent,
                tool_row=tool_row,
                tool_name=tool_name,
                pending_request=pending_request,
                policy_result=policy_result,
                terminal_event=AuditEventType.POLICY_BLOCKED,
            ),
        )
        return GatewayResult(
            status="BLOCKED",
            tool_name=tool_name,
            decision="BLOCK",
            reason=policy_result.reason,
            matched_policy=policy_result.matched_policy,
            policy_id=policy_id,
        )

    @staticmethod
    def _policy_matched_rows(
        *,
        execution: Execution,
        agent: Agent,
        tool_row: Tool,
        tool_name: str,
        pending_request: ToolRequest,
        policy_result: PolicyEvaluationResult,
        terminal_event: AuditEventType,
    ) -> Callable[[int], list[Any]]:
        def build_rows(seq: int) -> list[Any]:
            rows: list[Any] = []
            if policy_result.matched_policy:
                rows.append(
                    AuditEvent(
                        execution_id=execution.id,
                        sequence=seq,
                        event_type=AuditEventType.POLICY_MATCHED,
                        actor=agent.name,
                        event_metadata={
                            "tool_name": tool_name,
                            "matched_policy": policy_result.matched_policy,
                        },
                    )
                )
                seq += 1
            rows.append(
                AuditEvent(
                    execution_id=execution.id,
                    sequence=seq,
                    event_type=terminal_event,
                    actor=agent.name,
                    event_metadata={"tool_name": tool_name, "reason": policy_result.reason},
                )
            )
            rows.append(
                PolicyDecision(
                    execution_id=execution.id,
                    agent_id=agent.id,
                    tool_id=tool_row.id,
                    tool_request_id=pending_request.id,
                    decision=policy_result.decision,
                    matched_policy_id=policy_result.policy_id,
                    matched_policy_key=policy_result.matched_policy,
                    reason=policy_result.reason,
                    evaluated_context=policy_result.context,
                )
            )
            rows.append(pending_request)
            return rows

        return build_rows

    def _execute_and_record(
        self,
        *,
        db: Session,
        agent: Agent,
        execution: Execution,
        tool: Any,
        tool_name: str,
        arguments: dict[str, Any],
        tool_request: ToolRequest,
        decision_label: str,
        matched_policy: str | None = None,
        policy_id: str | None = None,
    ) -> GatewayResult:
        try:
            result = tool.execute(arguments, db)
        except Exception:
            # A tool may leave the session in a failed transaction. Restore it
            # before recording the gateway-level failure; never retry execution.
            db.rollback()
            error = {
                "code": "TOOL_EXECUTION_ERROR",
                "message": "Tool execution raised an unexpected error",
            }
            tool_request.status = ToolRequestStatus.FAILED
            tool_request.completed_at = datetime.now(UTC)
            tool_request.error = error
            self._commit_chunk(
                db,
                execution.id,
                lambda seq: [
                    AuditEvent(
                        execution_id=execution.id,
                        sequence=seq,
                        event_type=AuditEventType.TOOL_FAILED,
                        actor=agent.name,
                        event_metadata={"tool_name": tool_name, "error": error},
                    ),
                    tool_request,
                ],
            )
            return GatewayResult(
                status="FAILED",
                tool_name=tool_name,
                decision=decision_label,
                reason=error["message"],
                matched_policy=matched_policy,
                policy_id=policy_id,
            )

        if result.success:
            tool_request.status = ToolRequestStatus.EXECUTED
            tool_request.completed_at = datetime.now(UTC)
            tool_request.result = result.data
            self._commit_chunk(
                db,
                execution.id,
                lambda seq: [
                    AuditEvent(
                        execution_id=execution.id,
                        sequence=seq,
                        event_type=AuditEventType.TOOL_EXECUTED,
                        actor=agent.name,
                        event_metadata={"tool_name": tool_name},
                    ),
                    tool_request,
                ],
            )
            return GatewayResult(
                status="EXECUTED",
                tool_name=tool_name,
                tool_result=result.data,
                decision=decision_label,
                matched_policy=matched_policy,
                policy_id=policy_id,
            )

        error = result.error.model_dump() if result.error else {"code": "UNKNOWN", "message": ""}
        tool_request.status = ToolRequestStatus.FAILED
        tool_request.completed_at = datetime.now(UTC)
        tool_request.error = error
        self._commit_chunk(
            db,
            execution.id,
            lambda seq: [
                AuditEvent(
                    execution_id=execution.id,
                    sequence=seq,
                    event_type=AuditEventType.TOOL_FAILED,
                    actor=agent.name,
                    event_metadata={"tool_name": tool_name, "error": error},
                ),
                tool_request,
            ],
        )
        return GatewayResult(
            status="FAILED",
            tool_name=tool_name,
            decision=decision_label,
            reason=error.get("message"),
            matched_policy=matched_policy,
            policy_id=policy_id,
        )

    @staticmethod
    def _commit_chunk(
        db: Session, execution_id: uuid.UUID, build_rows: Callable[[int], list[Any]]
    ) -> None:
        for attempt in range(5):
            base_seq = (
                db.scalar(
                    select(func.max(AuditEvent.sequence)).where(
                        AuditEvent.execution_id == execution_id
                    )
                )
                or 0
            ) + 1
            for row in build_rows(base_seq):
                db.add(row)
            try:
                db.commit()
                return
            except IntegrityError as exc:
                db.rollback()
                constraint_name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
                if constraint_name != "uq_audit_events_execution_sequence":
                    raise
                if attempt == 4:
                    raise
