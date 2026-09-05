import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import (
    Agent,
    AgentToolPermission,
    AuditEvent,
    Execution,
    PolicyDecision,
    RiskAssessment,
    SecurityIncident,
    Tool,
    ToolRequest,
)
from app.models.enums import (
    AuditEventType,
    ExecutionStatus,
    IncidentStatus,
    IncidentType,
    PermissionType,
    PolicyAction,
    ToolRequestStatus,
)
from app.services.approval_engine import ApprovalEngine
from app.services.audit import commit_chunk
from app.services.policy_engine import PolicyEvaluationResult, policy_engine
from app.services.risk_engine import RiskAssessmentResult, combine_decisions, risk_engine
from app.tools import ToolNotFoundError, tool_registry

approval_engine = ApprovalEngine()

NON_EXECUTABLE_STATUSES = {
    ExecutionStatus.COMPLETED,
    ExecutionStatus.FAILED,
    ExecutionStatus.BLOCKED,
}

# The highest-severity signal present decides the SecurityIncident's
# incident_type when a risk-driven block involves more than one signal.
_INCIDENT_TYPE_PRIORITY = [
    "PROMPT_INJECTION",
    "PRIVILEGE_ESCALATION",
    "DATA_EXFILTRATION",
    "DESTRUCTIVE_ACTION",
    "SCOPE_DEVIATION",
    "SENSITIVE_DATA_ACCESS",
    "EXTERNAL_COMMUNICATION",
    "FINANCIAL_RISK",
    "UNUSUAL_TOOL_SEQUENCE",
]


class ApprovalStateConflictError(RuntimeError):
    pass


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
    approval_request_id: str | None = None
    risk_score: int | None = None
    risk_level: str | None = None
    risk_signals: list[str] | None = None


class ToolGateway:
    def execute(
        self,
        *,
        agent_id: uuid.UUID,
        execution_id: uuid.UUID,
        tool_name: str,
        arguments: dict[str, Any],
        db: Session,
        context: dict[str, Any] | None = None,
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

        if execution.status == ExecutionStatus.WAITING_APPROVAL:
            return GatewayResult(
                status="FAILED",
                tool_name=tool_name,
                reason="Execution is waiting for approval and cannot accept new tool calls",
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

            def build_unknown_tool_rows(seq: int) -> list[Any]:
                request = ToolRequest(
                    execution_id=execution.id,
                    agent_id=agent.id,
                    tool_id=None,
                    tool_name=tool_name,
                    arguments=arguments,
                    status=ToolRequestStatus.FAILED,
                    completed_at=datetime.now(UTC),
                    error={"code": "TOOL_NOT_FOUND", "message": f"No tool named '{tool_name}'"},
                )
                return [
                    AuditEvent(
                        execution_id=execution.id,
                        sequence=seq,
                        event_type=AuditEventType.TOOL_FAILED,
                        actor=agent.name,
                        event_metadata={"reason": "unknown tool"},
                    ),
                    request,
                ]

            self._commit_chunk(db, execution.id, build_unknown_tool_rows)
            return GatewayResult(status="FAILED", tool_name=tool_name, reason="Unknown tool")

        tool_row = db.scalar(select(Tool).where(Tool.name == tool_name))

        try:
            tool.input_schema.model_validate(arguments)
        except ValidationError as exc:
            validation_message = str(exc)

            def build_invalid_args_rows(seq: int) -> list[Any]:
                request = ToolRequest(
                    execution_id=execution.id,
                    agent_id=agent.id,
                    tool_id=tool_row.id if tool_row else None,
                    tool_name=tool_name,
                    arguments=arguments,
                    status=ToolRequestStatus.FAILED,
                    completed_at=datetime.now(UTC),
                    error={"code": "INVALID_ARGUMENTS", "message": validation_message},
                )
                return [
                    AuditEvent(
                        execution_id=execution.id,
                        sequence=seq,
                        event_type=AuditEventType.TOOL_FAILED,
                        actor=agent.name,
                        event_metadata={"reason": "invalid arguments"},
                    ),
                    request,
                ]

            self._commit_chunk(db, execution.id, build_invalid_args_rows)
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

            def build_deny_rows(seq: int) -> list[Any]:
                request = ToolRequest(
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
                )
                return [
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
                    request,
                ]

            self._commit_chunk(db, execution.id, build_deny_rows)
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
                context=context,
            )

        # Direct ALLOW. Risk still runs -- permission alone never bypasses it.
        return self._handle_direct_allow(
            db=db,
            agent=agent,
            execution=execution,
            tool=tool,
            tool_row=tool_row,
            tool_name=tool_name,
            arguments=arguments,
            context=context,
        )

    def _handle_direct_allow(
        self,
        *,
        db: Session,
        agent: Agent,
        execution: Execution,
        tool: Any,
        tool_row: Tool,
        tool_name: str,
        arguments: dict[str, Any],
        context: dict[str, Any] | None,
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
                    event_metadata={"tool_name": tool_name, "permission": "ALLOW"},
                ),
                pending_request,
            ],
        )

        # No real Policy row backs a direct ALLOW. Synthesize one so every
        # RiskAssessment/ApprovalRequest still has a real PolicyDecision to
        # reference, keeping that FK non-nullable on ApprovalRequest.
        policy_decision_id = uuid.uuid4()
        synthetic_policy_decision = PolicyDecision(
            id=policy_decision_id,
            execution_id=execution.id,
            agent_id=agent.id,
            tool_id=tool_row.id,
            tool_request_id=pending_request.id,
            decision=PolicyAction.ALLOW,
            matched_policy_id=None,
            matched_policy_key=None,
            reason="Direct permission ALLOW",
            evaluated_context={},
        )

        return self._assess_risk_and_finalize(
            db=db,
            agent=agent,
            execution=execution,
            tool=tool,
            tool_row=tool_row,
            tool_name=tool_name,
            arguments=arguments,
            context=context,
            pending_request=pending_request,
            policy_decision_id=policy_decision_id,
            effective_policy_action=PolicyAction.ALLOW,
            policy_reason="Direct permission ALLOW",
            matched_policy=None,
            policy_id=None,
            extra_risk_chunk_rows=[synthetic_policy_decision],
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
        context: dict[str, Any] | None,
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

        if policy_result.decision == PolicyAction.BLOCK:
            # No matching-decision BLOCK ever needs risk: it cannot get any
            # less blocked, and there's nothing left to escalate.
            def build_block_rows(seq: int) -> list[Any]:
                pending_request.status = ToolRequestStatus.DENIED
                pending_request.completed_at = datetime.now(UTC)
                pending_request.error = {
                    "code": "POLICY_BLOCKED",
                    "message": policy_result.reason,
                }
                return self._policy_outcome_rows(
                    execution=execution,
                    agent=agent,
                    tool_row=tool_row,
                    tool_name=tool_name,
                    pending_request=pending_request,
                    policy_decision_id=uuid.uuid4(),
                    policy_result=policy_result,
                    terminal_event=AuditEventType.POLICY_BLOCKED,
                    seq=seq,
                )

            self._commit_chunk(db, execution.id, build_block_rows)
            return GatewayResult(
                status="BLOCKED",
                tool_name=tool_name,
                decision="BLOCK",
                reason=policy_result.reason,
                matched_policy=policy_result.matched_policy,
                policy_id=policy_id,
            )

        # ALLOW or REQUIRE_APPROVAL: record policy's own decision durably,
        # then risk assessment runs and may only preserve or escalate it.
        policy_decision_id = uuid.uuid4()
        terminal_event = (
            AuditEventType.POLICY_ALLOWED
            if policy_result.decision == PolicyAction.ALLOW
            else AuditEventType.POLICY_APPROVAL_REQUIRED
        )

        def build_policy_outcome_rows(seq: int) -> list[Any]:
            pending_request.status = ToolRequestStatus.REQUESTED
            return self._policy_outcome_rows(
                execution=execution,
                agent=agent,
                tool_row=tool_row,
                tool_name=tool_name,
                pending_request=pending_request,
                policy_decision_id=policy_decision_id,
                policy_result=policy_result,
                terminal_event=terminal_event,
                seq=seq,
            )

        self._commit_chunk(db, execution.id, build_policy_outcome_rows)

        return self._assess_risk_and_finalize(
            db=db,
            agent=agent,
            execution=execution,
            tool=tool,
            tool_row=tool_row,
            tool_name=tool_name,
            arguments=arguments,
            context=context,
            pending_request=pending_request,
            policy_decision_id=policy_decision_id,
            effective_policy_action=policy_result.decision,
            policy_reason=policy_result.reason,
            matched_policy=policy_result.matched_policy,
            policy_id=policy_id,
            extra_risk_chunk_rows=[],
        )

    @staticmethod
    def _policy_outcome_rows(
        *,
        execution: Execution,
        agent: Agent,
        tool_row: Tool,
        tool_name: str,
        pending_request: ToolRequest,
        policy_decision_id: uuid.UUID,
        policy_result: PolicyEvaluationResult,
        terminal_event: AuditEventType,
        seq: int,
    ) -> list[Any]:
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
                id=policy_decision_id,
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

    def _assess_risk_and_finalize(
        self,
        *,
        db: Session,
        agent: Agent,
        execution: Execution,
        tool: Any,
        tool_row: Tool,
        tool_name: str,
        arguments: dict[str, Any],
        context: dict[str, Any] | None,
        pending_request: ToolRequest,
        policy_decision_id: uuid.UUID,
        effective_policy_action: PolicyAction,
        policy_reason: str,
        matched_policy: str | None,
        policy_id: str | None,
        extra_risk_chunk_rows: list[Any],
    ) -> GatewayResult:
        try:
            risk_result = risk_engine.assess(
                agent=agent,
                execution=execution,
                tool=tool_row,
                arguments=arguments,
                policy_decision=effective_policy_action,
                context=context,
                db=db,
            )
        except Exception:
            # Same fail-closed contract as RiskEngine's own internal
            # handling: an unexpected failure here must never default to
            # ALLOW. RiskEngine already catches per-detector errors; this is
            # defense-in-depth for a bug anywhere else in assess() itself.
            db.rollback()
            risk_result = RiskAssessmentResult(
                risk_score=100,
                risk_level="CRITICAL",
                signals=[],
                reason_codes=["RISK_ASSESSMENT_ERROR"],
                recommended_action=PolicyAction.BLOCK,
                context={},
            )

        risk_assessment_id = uuid.uuid4()

        def build_risk_rows(seq: int) -> list[Any]:
            rows: list[Any] = [
                AuditEvent(
                    execution_id=execution.id,
                    sequence=seq,
                    event_type=AuditEventType.RISK_ASSESSMENT_STARTED,
                    actor=agent.name,
                    event_metadata={"tool_name": tool_name},
                )
            ]
            seq += 1
            for signal in risk_result.signals:
                rows.append(
                    AuditEvent(
                        execution_id=execution.id,
                        sequence=seq,
                        event_type=AuditEventType.RISK_SIGNAL_DETECTED,
                        actor=agent.name,
                        event_metadata={"tool_name": tool_name, "signal": signal},
                    )
                )
                seq += 1
            rows.append(
                AuditEvent(
                    execution_id=execution.id,
                    sequence=seq,
                    event_type=AuditEventType.RISK_ASSESSED,
                    actor=agent.name,
                    event_metadata={
                        "tool_name": tool_name,
                        "risk_score": risk_result.risk_score,
                        "risk_level": risk_result.risk_level.value
                        if hasattr(risk_result.risk_level, "value")
                        else str(risk_result.risk_level),
                    },
                )
            )
            rows.append(
                RiskAssessment(
                    id=risk_assessment_id,
                    execution_id=execution.id,
                    agent_id=agent.id,
                    tool_request_id=pending_request.id,
                    tool_id=tool_row.id,
                    policy_decision_id=policy_decision_id,
                    risk_score=risk_result.risk_score,
                    risk_level=risk_result.risk_level,
                    signals=risk_result.signals,
                    reason_codes=risk_result.reason_codes,
                    assessment_context=risk_result.context,
                    recommended_action=risk_result.recommended_action,
                )
            )
            rows.extend(extra_risk_chunk_rows)
            return rows

        self._commit_chunk(db, execution.id, build_risk_rows)

        final_decision = combine_decisions(effective_policy_action, risk_result.recommended_action)
        escalated = final_decision != effective_policy_action

        base_result_kwargs = {
            "tool_name": tool_name,
            "matched_policy": matched_policy,
            "policy_id": policy_id,
            "risk_score": risk_result.risk_score,
            "risk_level": risk_result.risk_level.value
            if hasattr(risk_result.risk_level, "value")
            else str(risk_result.risk_level),
            "risk_signals": risk_result.signals,
        }

        if final_decision == PolicyAction.BLOCK:
            return self._finalize_risk_block(
                db=db,
                agent=agent,
                execution=execution,
                tool_name=tool_name,
                pending_request=pending_request,
                risk_result=risk_result,
                risk_assessment_id=risk_assessment_id,
                escalated=escalated,
                base_result_kwargs=base_result_kwargs,
            )

        if final_decision == PolicyAction.REQUIRE_APPROVAL:
            if escalated:
                codes = risk_result.reason_codes or ["RISK_ESCALATION"]
                approval_reason = f"Escalated by Risk Engine: {', '.join(codes)}"
            else:
                approval_reason = policy_reason
            return self._create_approval_and_commit(
                db=db,
                agent=agent,
                execution=execution,
                tool_row=tool_row,
                tool_name=tool_name,
                arguments=arguments,
                pending_request=pending_request,
                policy_decision_id=policy_decision_id,
                reason=approval_reason,
                escalated=escalated,
                matched_policy=matched_policy,
                policy_id=policy_id,
                base_result_kwargs=base_result_kwargs,
            )

        # ALLOW. Risk can only preserve or escalate, so a final ALLOW here
        # always means effective_policy_action was already ALLOW -- never
        # actually an escalation.
        self._commit_chunk(
            db,
            execution.id,
            lambda seq: [
                AuditEvent(
                    execution_id=execution.id,
                    sequence=seq,
                    event_type=AuditEventType.ACTION_ALLOWED,
                    actor=agent.name,
                    event_metadata={"tool_name": tool_name},
                )
            ],
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
            matched_policy=matched_policy,
            policy_id=policy_id,
            extra_result_kwargs={
                "risk_score": risk_result.risk_score,
                "risk_level": base_result_kwargs["risk_level"],
                "risk_signals": risk_result.signals,
            },
        )

    def _finalize_risk_block(
        self,
        *,
        db: Session,
        agent: Agent,
        execution: Execution,
        tool_name: str,
        pending_request: ToolRequest,
        risk_result: RiskAssessmentResult,
        risk_assessment_id: uuid.UUID,
        escalated: bool,
        base_result_kwargs: dict[str, Any],
    ) -> GatewayResult:
        incident_id = uuid.uuid4()
        create_incident = bool(risk_result.signals)
        incident_type_name = next(
            (s for s in _INCIDENT_TYPE_PRIORITY if s in risk_result.signals),
            risk_result.signals[0] if risk_result.signals else None,
        )

        def build_block_rows(seq: int) -> list[Any]:
            pending_request.status = ToolRequestStatus.DENIED
            pending_request.completed_at = datetime.now(UTC)
            pending_request.error = {
                "code": "RISK_BLOCKED",
                "message": f"Blocked by risk engine (score={risk_result.risk_score})",
            }
            rows: list[Any] = []
            if escalated:
                rows.append(
                    AuditEvent(
                        execution_id=execution.id,
                        sequence=seq,
                        event_type=AuditEventType.RISK_ESCALATED,
                        actor=agent.name,
                        event_metadata={"tool_name": tool_name},
                    )
                )
                seq += 1
            rows.append(
                AuditEvent(
                    execution_id=execution.id,
                    sequence=seq,
                    event_type=AuditEventType.ACTION_BLOCKED_BY_RISK,
                    actor=agent.name,
                    event_metadata={
                        "tool_name": tool_name,
                        "risk_score": risk_result.risk_score,
                    },
                )
            )
            seq += 1
            rows.append(pending_request)
            if create_incident and incident_type_name is not None:
                rows.append(
                    SecurityIncident(
                        id=incident_id,
                        execution_id=execution.id,
                        agent_id=agent.id,
                        tool_request_id=pending_request.id,
                        risk_assessment_id=risk_assessment_id,
                        incident_type=IncidentType(incident_type_name),
                        severity=risk_result.risk_level,
                        title=f"Blocked {tool_name} call ({incident_type_name})",
                        description=(
                            f"Risk Engine blocked a {tool_name} call with score "
                            f"{risk_result.risk_score} due to signals: "
                            f"{', '.join(risk_result.signals)}."
                        ),
                        indicators=risk_result.reason_codes,
                        status=IncidentStatus.OPEN,
                    )
                )
                rows.append(
                    AuditEvent(
                        execution_id=execution.id,
                        sequence=seq,
                        event_type=AuditEventType.SECURITY_INCIDENT_CREATED,
                        actor=agent.name,
                        event_metadata={
                            "tool_name": tool_name,
                            "incident_type": incident_type_name,
                        },
                    )
                )
            return rows

        self._commit_chunk(db, execution.id, build_block_rows)

        return GatewayResult(
            status="BLOCKED",
            decision="BLOCK",
            reason=f"Blocked by risk engine (score={risk_result.risk_score})",
            **base_result_kwargs,
        )

    def _create_approval_and_commit(
        self,
        *,
        db: Session,
        agent: Agent,
        execution: Execution,
        tool_row: Tool,
        tool_name: str,
        arguments: dict[str, Any],
        pending_request: ToolRequest,
        policy_decision_id: uuid.UUID,
        reason: str,
        escalated: bool,
        matched_policy: str | None,
        policy_id: str | None,
        base_result_kwargs: dict[str, Any],
    ) -> GatewayResult:
        approval_requested_at = datetime.now(UTC)
        approval_id = uuid.uuid4()
        approval_reason = reason
        approval = approval_engine.create_approval(
            approval_id=approval_id,
            execution_id=execution.id,
            agent_id=agent.id,
            tool_request_id=pending_request.id,
            policy_decision_id=policy_decision_id,
            tool_name=tool_name,
            arguments=arguments,
            risk_level=tool_row.risk_category,
            reason=approval_reason,
        )

        def build_rows(seq: int) -> list[Any]:
            # Atomically admit only one pending approval per execution. Two
            # concurrent gateway calls may both have read RUNNING before
            # either reaches this point.
            transitioned = db.execute(
                update(Execution)
                .where(
                    Execution.id == execution.id,
                    Execution.status == ExecutionStatus.RUNNING,
                )
                .values(status=ExecutionStatus.WAITING_APPROVAL)
            ).rowcount
            if transitioned == 0:
                raise ApprovalStateConflictError

            # commit_chunk may roll the session back after an audit-sequence
            # collision. Reapply transient request state on every attempt.
            pending_request.status = ToolRequestStatus.REQUIRES_APPROVAL
            pending_request.completed_at = approval_requested_at

            rows: list[Any] = []
            if escalated:
                rows.append(
                    AuditEvent(
                        execution_id=execution.id,
                        sequence=seq,
                        event_type=AuditEventType.RISK_ESCALATED,
                        actor=agent.name,
                        event_metadata={"tool_name": tool_name},
                    )
                )
                seq += 1
            rows.append(
                AuditEvent(
                    execution_id=execution.id,
                    sequence=seq,
                    event_type=AuditEventType.APPROVAL_REQUESTED,
                    actor=agent.name,
                    event_metadata={
                        "approval_id": str(approval_id),
                        "tool_name": tool_name,
                    },
                )
            )
            rows.append(pending_request)
            rows.append(approval)
            return rows

        try:
            self._commit_chunk(db, execution.id, build_rows)
        except ApprovalStateConflictError:
            db.rollback()
            return GatewayResult(
                status="FAILED",
                decision="REQUIRE_APPROVAL",
                reason="Execution is already waiting for approval",
                **base_result_kwargs,
            )
        return GatewayResult(
            status="REQUIRES_APPROVAL",
            decision="REQUIRE_APPROVAL",
            reason=approval_reason,
            approval_request_id=str(approval_id),
            **base_result_kwargs,
        )

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
        extra_result_kwargs: dict[str, Any] | None = None,
    ) -> GatewayResult:
        extra_result_kwargs = extra_result_kwargs or {}
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
            completed_at = datetime.now(UTC)

            def build_exception_rows(seq: int) -> list[Any]:
                tool_request.status = ToolRequestStatus.FAILED
                tool_request.completed_at = completed_at
                tool_request.error = error
                return [
                    AuditEvent(
                        execution_id=execution.id,
                        sequence=seq,
                        event_type=AuditEventType.TOOL_FAILED,
                        actor=agent.name,
                        event_metadata={"tool_name": tool_name, "error": error},
                    ),
                    tool_request,
                ]

            self._commit_chunk(db, execution.id, build_exception_rows)
            return GatewayResult(
                status="FAILED",
                tool_name=tool_name,
                decision=decision_label,
                reason=error["message"],
                matched_policy=matched_policy,
                policy_id=policy_id,
                **extra_result_kwargs,
            )

        if result.success:
            completed_at = datetime.now(UTC)

            def build_success_rows(seq: int) -> list[Any]:
                tool_request.status = ToolRequestStatus.EXECUTED
                tool_request.completed_at = completed_at
                tool_request.result = result.data
                return [
                    AuditEvent(
                        execution_id=execution.id,
                        sequence=seq,
                        event_type=AuditEventType.TOOL_EXECUTED,
                        actor=agent.name,
                        event_metadata={"tool_name": tool_name},
                    ),
                    tool_request,
                ]

            self._commit_chunk(db, execution.id, build_success_rows)
            return GatewayResult(
                status="EXECUTED",
                tool_name=tool_name,
                tool_result=result.data,
                decision=decision_label,
                matched_policy=matched_policy,
                policy_id=policy_id,
                **extra_result_kwargs,
            )

        error = result.error.model_dump() if result.error else {"code": "UNKNOWN", "message": ""}
        completed_at = datetime.now(UTC)

        def build_failure_rows(seq: int) -> list[Any]:
            tool_request.status = ToolRequestStatus.FAILED
            tool_request.completed_at = completed_at
            tool_request.error = error
            return [
                AuditEvent(
                    execution_id=execution.id,
                    sequence=seq,
                    event_type=AuditEventType.TOOL_FAILED,
                    actor=agent.name,
                    event_metadata={"tool_name": tool_name, "error": error},
                ),
                tool_request,
            ]

        self._commit_chunk(db, execution.id, build_failure_rows)
        return GatewayResult(
            status="FAILED",
            tool_name=tool_name,
            decision=decision_label,
            reason=error.get("message"),
            matched_policy=matched_policy,
            policy_id=policy_id,
            **extra_result_kwargs,
        )

    @staticmethod
    def _commit_chunk(
        db: Session, execution_id: uuid.UUID, build_rows: Callable[[int], list[Any]]
    ) -> None:
        commit_chunk(db, execution_id, build_rows)
