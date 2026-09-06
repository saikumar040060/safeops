"""Agent Runtime: plans and executes multi-step agent workflows.

AgentRuntime NEVER calls a tool directly -- it holds no reference to
BaseTool, ToolRegistry, or any concrete tool module. The only way it can
cause a side effect is `self.gateway.execute(...)`, which is exactly the
same ToolGateway used by Milestones 4-7 (permission -> policy -> risk ->
approval -> execution -> audit). A planner's output is always one of three
Pydantic-validated shapes (ToolAction / Complete / Fail); nothing it
returns is ever eval'd, imported, or dispatched dynamically -- a ToolAction
is just data that gets forwarded to ToolGateway.execute(), which does its
own independent validation of the tool name and arguments.

Concurrency: step() and resume() each open by atomically claiming
Execution.stepping (an ordinary `UPDATE ... WHERE stepping = false`,
committed immediately) before doing any planning or calling the gateway,
and release it in a `finally` once the whole plan-execute-finalize
critical section is done. A losing concurrent caller sees the claim
UPDATE match zero rows and returns CONFLICT immediately -- it never
calls the planner or ToolGateway. This claim is plain transactional row
data rather than a Postgres session-level advisory lock deliberately:
SQLAlchemy sessions do not pin one physical connection across the many
small commits this section makes internally, so a lock acquired on one
pooled connection could end up "released" on a different one and never
actually clear. Forward progress is additionally recorded via an INSERT
into execution_steps under a UNIQUE(execution_id, sequence) constraint,
the same pattern audit_events uses.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Agent, ApprovalRequest, AuditEvent, Execution, ExecutionStep, ToolRequest
from app.models.enums import (
    ApprovalStatus,
    AuditEventType,
    ExecutionStatus,
    StepStatus,
    StepType,
    ToolRequestStatus,
)
from app.services.audit import commit_chunk
from app.services.planner import Complete, DeterministicPlanner, Fail, Planner, ToolAction
from app.services.tool_gateway import ToolGateway

READ_ONLY_TOOLS = {
    "read_customer",
    "get_payments",
    "get_support_ticket",
    "read_logs",
    "get_deployment",
}

TERMINAL_EXECUTION_STATUSES = {
    ExecutionStatus.COMPLETED,
    ExecutionStatus.FAILED,
    ExecutionStatus.BLOCKED,
    ExecutionStatus.CANCELLED,
}


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


class RuntimeResult(BaseModel):
    status: str
    execution_status: str
    execution_id: str | None = None
    reason: str | None = None
    tool_name: str | None = None
    approval_request_id: str | None = None
    step_sequence: int | None = None


@dataclass
class _ResolvedApprovalOutcome:
    status: str
    reason: str | None
    should_continue: bool


class AgentRuntime:
    def __init__(self, *, planner: Planner | None = None, gateway: ToolGateway | None = None):
        self.planner = planner or DeterministicPlanner()
        self.gateway = gateway or ToolGateway()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_execution(
        self,
        *,
        agent_id: uuid.UUID,
        objective: str,
        db: Session,
        context: dict[str, Any] | None = None,
    ) -> RuntimeResult:
        agent = db.get(Agent, agent_id)
        if agent is None:
            return RuntimeResult(
                status="NOT_FOUND", execution_status="UNKNOWN", reason="Agent not found"
            )

        safe_context = _json_safe(context) if isinstance(context, dict) else {}
        execution = Execution(
            agent_id=agent.id,
            objective=objective,
            status=ExecutionStatus.CREATED,
            initial_context=safe_context,
        )
        db.add(execution)
        db.commit()
        db.refresh(execution)

        def build_rows(seq: int) -> list[Any]:
            transitioned = db.execute(
                update(Execution)
                .where(Execution.id == execution.id, Execution.status == ExecutionStatus.CREATED)
                .values(status=ExecutionStatus.RUNNING)
            ).rowcount
            if transitioned:
                execution.status = ExecutionStatus.RUNNING
            return [
                AuditEvent(
                    execution_id=execution.id,
                    sequence=seq,
                    event_type=AuditEventType.EXECUTION_STARTED,
                    actor=agent.name,
                    event_metadata={"objective": objective},
                )
            ]

        commit_chunk(db, execution.id, build_rows)

        return RuntimeResult(
            status="CREATED",
            execution_status=execution.status.value,
            execution_id=str(execution.id),
        )

    def step(self, execution_id: uuid.UUID, db: Session) -> RuntimeResult:
        execution = db.get(Execution, execution_id)
        if execution is None:
            return RuntimeResult(
                status="NOT_FOUND", execution_status="UNKNOWN", reason="Execution not found"
            )
        if execution.status != ExecutionStatus.RUNNING:
            return RuntimeResult(
                status="NOOP",
                execution_status=execution.status.value,
                reason=f"Execution is {execution.status.value}, cannot step",
            )

        if not self._claim_stepping(db, execution):
            return self._conflict_result(execution)
        try:
            if execution.status != ExecutionStatus.RUNNING:
                return RuntimeResult(
                    status="NOOP",
                    execution_status=execution.status.value,
                    reason=f"Execution is {execution.status.value}, cannot step",
                )
            return self._advance(db, execution)
        finally:
            self._release_stepping(db, execution_id)

    def resume(self, execution_id: uuid.UUID, db: Session) -> RuntimeResult:
        execution = db.get(Execution, execution_id)
        if execution is None:
            return RuntimeResult(
                status="NOT_FOUND", execution_status="UNKNOWN", reason="Execution not found"
            )
        if execution.status == ExecutionStatus.WAITING_APPROVAL:
            return RuntimeResult(
                status="NOOP",
                execution_status=execution.status.value,
                reason="Still waiting for approval",
            )
        if execution.status != ExecutionStatus.RUNNING:
            return RuntimeResult(
                status="NOOP",
                execution_status=execution.status.value,
                reason=f"Execution is {execution.status.value}, cannot resume",
            )

        if not self._claim_stepping(db, execution):
            return self._conflict_result(execution)
        try:
            if execution.status != ExecutionStatus.RUNNING:
                return RuntimeResult(
                    status="NOOP",
                    execution_status=execution.status.value,
                    reason=f"Execution is {execution.status.value}, cannot resume",
                )

            pending_step = db.scalar(
                select(ExecutionStep)
                .where(
                    ExecutionStep.execution_id == execution.id,
                    ExecutionStep.status == StepStatus.WAITING_APPROVAL,
                )
                .order_by(ExecutionStep.sequence.desc())
                .limit(1)
            )
            if pending_step is None:
                return RuntimeResult(
                    status="NOOP",
                    execution_status=execution.status.value,
                    reason="No pending approval step to resume from",
                )

            outcome = self._resolve_pending_step(db, execution, pending_step)
            if outcome.status != "NOOP":
                commit_chunk(
                    db,
                    execution.id,
                    lambda seq: [
                        AuditEvent(
                            execution_id=execution.id,
                            sequence=seq,
                            event_type=AuditEventType.EXECUTION_RESUMED,
                            actor="agent-runtime",
                            event_metadata={"step_sequence": pending_step.sequence},
                        )
                    ],
                )

            if not outcome.should_continue:
                return RuntimeResult(
                    status=outcome.status,
                    execution_status=execution.status.value,
                    reason=outcome.reason,
                    step_sequence=pending_step.sequence,
                )

            return self._advance(db, execution)
        finally:
            self._release_stepping(db, execution_id)

    @staticmethod
    def _claim_stepping(db: Session, execution: Execution) -> bool:
        claimed = (
            db.execute(
                update(Execution)
                .where(Execution.id == execution.id, Execution.stepping.is_(False))
                .values(stepping=True)
            ).rowcount
            > 0
        )
        db.commit()
        db.refresh(execution)
        return claimed

    @staticmethod
    def _release_stepping(db: Session, execution_id: uuid.UUID) -> None:
        db.execute(
            update(Execution).where(Execution.id == execution_id).values(stepping=False)
        )
        db.commit()

    def cancel(self, execution_id: uuid.UUID, db: Session) -> RuntimeResult:
        execution = db.get(Execution, execution_id)
        if execution is None:
            return RuntimeResult(
                status="NOT_FOUND", execution_status="UNKNOWN", reason="Execution not found"
            )

        now = datetime.now(UTC)
        transitioned = db.execute(
            update(Execution)
            .where(
                Execution.id == execution.id,
                Execution.status.in_([ExecutionStatus.RUNNING, ExecutionStatus.WAITING_APPROVAL]),
            )
            .values(status=ExecutionStatus.CANCELLED, completed_at=now)
        ).rowcount
        db.commit()
        db.refresh(execution)

        if not transitioned:
            return RuntimeResult(
                status="NOOP",
                execution_status=execution.status.value,
                reason=f"Cannot cancel execution in status {execution.status.value}",
            )

        commit_chunk(
            db,
            execution.id,
            lambda seq: [
                AuditEvent(
                    execution_id=execution.id,
                    sequence=seq,
                    event_type=AuditEventType.EXECUTION_CANCELLED,
                    actor="agent-runtime",
                    event_metadata={},
                )
            ],
        )
        return RuntimeResult(status="CANCELLED", execution_status=execution.status.value)

    # ------------------------------------------------------------------
    # Internal: the shared step-claiming/advancing core
    # ------------------------------------------------------------------

    def _advance(self, db: Session, execution: Execution) -> RuntimeResult:
        history = self._load_history(db, execution.id)
        context = {"objective": execution.objective, "initial_context": execution.initial_context}

        try:
            decision = self.planner.next_action(execution, context, history)
        except Exception:
            # Planner exceptions must fail closed, never leak internals into
            # persisted state or the caller-facing result.
            decision = Fail(reason="Planner raised an unexpected error", code="PLANNER_ERROR")

        if not isinstance(decision, ToolAction | Complete | Fail):
            decision = Fail(
                reason="Planner returned an unrecognized decision type",
                code="PLANNER_MALFORMED_OUTPUT",
            )

        if isinstance(decision, Complete):
            step = self._claim_step(
                db,
                execution.id,
                StepType.FINAL,
                {"decision": "COMPLETE", "reason": decision.reason},
            )
            if step is None:
                return self._conflict_result(execution)
            self._finalize(
                db,
                execution,
                step,
                StepStatus.COMPLETED,
                {"reason": decision.reason},
                AuditEventType.EXECUTION_COMPLETED,
                {"reason": decision.reason},
                terminal_status=ExecutionStatus.COMPLETED,
            )
            return RuntimeResult(
                status="COMPLETED",
                execution_status=execution.status.value,
                reason=decision.reason,
                step_sequence=step.sequence,
            )

        if isinstance(decision, Fail):
            step = self._claim_step(
                db,
                execution.id,
                StepType.FINAL,
                {"decision": "FAIL", "reason": decision.reason, "code": decision.code},
            )
            if step is None:
                return self._conflict_result(execution)
            self._finalize(
                db,
                execution,
                step,
                StepStatus.FAILED,
                {"reason": decision.reason, "code": decision.code},
                AuditEventType.EXECUTION_FAILED,
                {"reason": decision.reason, "code": decision.code},
                terminal_status=ExecutionStatus.FAILED,
            )
            return RuntimeResult(
                status="FAILED",
                execution_status=execution.status.value,
                reason=decision.reason,
                step_sequence=step.sequence,
            )

        # ToolAction
        step_input = {
            "tool_name": decision.tool_name,
            "arguments": _json_safe(decision.arguments),
            "reason": decision.reason,
            "sources": [s.model_dump() for s in decision.sources],
        }
        step = self._claim_step(db, execution.id, StepType.TOOL_CALL, step_input)
        if step is None:
            return self._conflict_result(execution)

        commit_chunk(
            db,
            execution.id,
            lambda seq: [
                AuditEvent(
                    execution_id=execution.id,
                    sequence=seq,
                    event_type=AuditEventType.EXECUTION_STEP_STARTED,
                    actor="agent-runtime",
                    event_metadata={
                        "step_sequence": step.sequence,
                        "tool_name": decision.tool_name,
                    },
                )
            ],
        )

        return self._run_tool_call_step(db, execution, step, decision, allow_retry=True)

    def _run_tool_call_step(
        self,
        db: Session,
        execution: Execution,
        step: ExecutionStep,
        action: ToolAction,
        *,
        allow_retry: bool,
    ) -> RuntimeResult:
        result = self.gateway.execute(
            agent_id=execution.agent_id,
            execution_id=execution.id,
            tool_name=action.tool_name,
            arguments=action.arguments,
            db=db,
            context={"sources": [s.model_dump() for s in action.sources]},
        )
        tool_request_id = self._lookup_tool_request_id(db, execution.id, action.tool_name)
        output = result.model_dump()

        if result.status == "EXECUTED":
            self._finalize(
                db,
                execution,
                step,
                StepStatus.COMPLETED,
                output,
                AuditEventType.EXECUTION_STEP_COMPLETED,
                {"step_sequence": step.sequence, "tool_name": action.tool_name},
                tool_request_id=tool_request_id,
            )
            return RuntimeResult(
                status="EXECUTED",
                execution_status=execution.status.value,
                tool_name=action.tool_name,
                step_sequence=step.sequence,
            )

        if result.status == "REQUIRES_APPROVAL":
            self._finalize(
                db,
                execution,
                step,
                StepStatus.WAITING_APPROVAL,
                output,
                AuditEventType.EXECUTION_WAITING_APPROVAL,
                {
                    "step_sequence": step.sequence,
                    "tool_name": action.tool_name,
                    "approval_request_id": result.approval_request_id,
                },
                tool_request_id=tool_request_id,
            )
            db.refresh(execution)
            return RuntimeResult(
                status="WAITING_APPROVAL",
                execution_status=execution.status.value,
                approval_request_id=result.approval_request_id,
                tool_name=action.tool_name,
                step_sequence=step.sequence,
            )

        if result.status == "BLOCKED":
            self._finalize(
                db,
                execution,
                step,
                StepStatus.BLOCKED,
                output,
                AuditEventType.EXECUTION_BLOCKED,
                {
                    "step_sequence": step.sequence,
                    "tool_name": action.tool_name,
                    "reason": result.reason,
                },
                tool_request_id=tool_request_id,
                terminal_status=ExecutionStatus.BLOCKED,
            )
            return RuntimeResult(
                status="BLOCKED",
                execution_status=execution.status.value,
                reason=result.reason,
                tool_name=action.tool_name,
                step_sequence=step.sequence,
            )

        # FAILED: side-effecting tools never auto-retry. A read-only tool
        # may retry exactly once, and only once (allow_retry=False on the
        # recursive call prevents a retry loop).
        if allow_retry and action.tool_name in READ_ONLY_TOOLS:
            self._persist_step_only(db, step, StepStatus.FAILED, output, tool_request_id)
            retry_step = self._claim_step(
                db,
                execution.id,
                StepType.TOOL_CALL,
                {**step.input, "retry_of_sequence": step.sequence},
            )
            if retry_step is not None:
                return self._run_tool_call_step(
                    db, execution, retry_step, action, allow_retry=False
                )

        self._finalize(
            db,
            execution,
            step,
            StepStatus.FAILED,
            output,
            AuditEventType.EXECUTION_FAILED,
            {
                "step_sequence": step.sequence,
                "tool_name": action.tool_name,
                "reason": result.reason,
            },
            tool_request_id=tool_request_id,
            terminal_status=ExecutionStatus.FAILED,
        )
        return RuntimeResult(
            status="FAILED",
            execution_status=execution.status.value,
            reason=result.reason,
            tool_name=action.tool_name,
            step_sequence=step.sequence,
        )

    def _resolve_pending_step(
        self, db: Session, execution: Execution, step: ExecutionStep
    ) -> _ResolvedApprovalOutcome:
        approval_id_str = (step.output or {}).get("approval_request_id")
        approval = None
        if approval_id_str:
            try:
                approval = db.get(ApprovalRequest, uuid.UUID(approval_id_str))
            except ValueError:
                approval = None

        if approval is None or approval.status == ApprovalStatus.PENDING:
            return _ResolvedApprovalOutcome(
                status="NOOP", reason="Approval not yet resolved", should_continue=False
            )

        tool_request = db.get(ToolRequest, approval.tool_request_id)

        if approval.status == ApprovalStatus.REJECTED:
            output = {**(step.output or {}), "resolution": "REJECTED"}
            self._finalize(
                db,
                execution,
                step,
                StepStatus.BLOCKED,
                output,
                AuditEventType.EXECUTION_BLOCKED,
                {"step_sequence": step.sequence, "reason": "Approval rejected"},
                terminal_status=ExecutionStatus.BLOCKED,
            )
            return _ResolvedApprovalOutcome(
                status="BLOCKED", reason="Approval rejected", should_continue=False
            )

        if approval.status == ApprovalStatus.EXPIRED:
            output = {**(step.output or {}), "resolution": "EXPIRED"}
            self._finalize(
                db,
                execution,
                step,
                StepStatus.FAILED,
                output,
                AuditEventType.EXECUTION_FAILED,
                {"step_sequence": step.sequence, "reason": "Approval expired"},
                terminal_status=ExecutionStatus.FAILED,
            )
            return _ResolvedApprovalOutcome(
                status="FAILED", reason="Approval expired", should_continue=False
            )

        if approval.status == ApprovalStatus.EXECUTED:
            tool_succeeded = (
                tool_request is not None and tool_request.status == ToolRequestStatus.EXECUTED
            )
            output = {
                **(step.output or {}),
                "resolution": "EXECUTED",
                "tool_result": tool_request.result if tool_request else None,
            }
            if tool_succeeded:
                self._finalize(
                    db,
                    execution,
                    step,
                    StepStatus.COMPLETED,
                    output,
                    AuditEventType.EXECUTION_STEP_COMPLETED,
                    {"step_sequence": step.sequence},
                    tool_request_id=tool_request.id if tool_request else None,
                )
                return _ResolvedApprovalOutcome(
                    status="COMPLETED", reason=None, should_continue=True
                )

            self._finalize(
                db,
                execution,
                step,
                StepStatus.FAILED,
                output,
                AuditEventType.EXECUTION_FAILED,
                {"step_sequence": step.sequence, "reason": "Approved action failed"},
                tool_request_id=tool_request.id if tool_request else None,
                terminal_status=ExecutionStatus.FAILED,
            )
            return _ResolvedApprovalOutcome(
                status="FAILED", reason="Approved action failed", should_continue=False
            )

        # Approved but the approval engine hasn't finished executing it yet
        # (a narrow window between its own CAS and tool execution). Fail
        # closed: nothing to resume from until that finishes.
        return _ResolvedApprovalOutcome(
            status="NOOP", reason="Approval approved but not finished executing yet",
            should_continue=False,
        )

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_history(db: Session, execution_id: uuid.UUID) -> list[ExecutionStep]:
        return list(
            db.scalars(
                select(ExecutionStep)
                .where(ExecutionStep.execution_id == execution_id)
                .order_by(ExecutionStep.sequence)
            )
        )

    @staticmethod
    def _lookup_tool_request_id(
        db: Session, execution_id: uuid.UUID, tool_name: str
    ) -> uuid.UUID | None:
        return db.scalar(
            select(ToolRequest.id)
            .where(ToolRequest.execution_id == execution_id, ToolRequest.tool_name == tool_name)
            .order_by(ToolRequest.requested_at.desc())
            .limit(1)
        )

    @staticmethod
    def _claim_step(
        db: Session, execution_id: uuid.UUID, step_type: StepType, input_data: dict[str, Any]
    ) -> ExecutionStep | None:
        next_seq = (
            db.scalar(
                select(func.max(ExecutionStep.sequence)).where(
                    ExecutionStep.execution_id == execution_id
                )
            )
            or 0
        ) + 1
        step = ExecutionStep(
            execution_id=execution_id,
            sequence=next_seq,
            step_type=step_type,
            status=StepStatus.PENDING,
            input=input_data,
        )
        db.add(step)
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            constraint_name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
            if constraint_name != "uq_execution_steps_execution_sequence":
                raise
            return None
        db.refresh(step)
        return step

    @staticmethod
    def _persist_step_only(
        db: Session,
        step: ExecutionStep,
        status: StepStatus,
        output: dict[str, Any],
        tool_request_id: uuid.UUID | None,
    ) -> None:
        step.status = status
        step.output = output
        step.completed_at = datetime.now(UTC)
        if tool_request_id is not None:
            step.tool_request_id = tool_request_id
        db.add(step)
        db.commit()

    @staticmethod
    def _finalize(
        db: Session,
        execution: Execution,
        step: ExecutionStep,
        status: StepStatus,
        output: dict[str, Any],
        event_type: AuditEventType,
        event_metadata: dict[str, Any],
        *,
        tool_request_id: uuid.UUID | None = None,
        terminal_status: ExecutionStatus | None = None,
    ) -> None:
        completed_at = datetime.now(UTC)

        def build_rows(seq: int) -> list[Any]:
            # Reapplied on every commit_chunk retry attempt: a rollback on
            # collision expires these in-memory mutations.
            step.status = status
            step.output = output
            step.completed_at = completed_at
            if tool_request_id is not None:
                step.tool_request_id = tool_request_id
            rows: list[Any] = [step]
            if terminal_status is not None:
                transitioned = db.execute(
                    update(Execution)
                    .where(
                        Execution.id == execution.id,
                        Execution.status == ExecutionStatus.RUNNING,
                    )
                    .values(status=terminal_status, completed_at=completed_at)
                ).rowcount
                if transitioned:
                    execution.status = terminal_status
                    execution.completed_at = completed_at
            rows.append(
                AuditEvent(
                    execution_id=execution.id,
                    sequence=seq,
                    event_type=event_type,
                    actor="agent-runtime",
                    event_metadata=event_metadata,
                )
            )
            return rows

        commit_chunk(db, execution.id, build_rows)

    @staticmethod
    def _conflict_result(execution: Execution) -> RuntimeResult:
        return RuntimeResult(
            status="CONFLICT",
            execution_status=execution.status.value,
            reason="Another step is already in progress for this execution",
        )
