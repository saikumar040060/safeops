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

Concurrency: step() and resume() each open by atomically claiming a
TTL'd lease on the execution (`stepping` + `stepping_claim_id` +
`stepping_claimed_at`, an ordinary `UPDATE ... WHERE stepping = false OR
stepping_claimed_at < now() - LEASE_TTL`, committed immediately) before
doing any planning or calling the gateway, and release it in a `finally`
once the whole plan-execute-finalize critical section is done. A losing
concurrent caller sees the claim UPDATE match zero rows and returns
CONFLICT immediately -- it never calls the planner or ToolGateway. This
claim is plain transactional row data rather than a Postgres session-level
advisory lock deliberately: SQLAlchemy sessions do not pin one physical
connection across the many small commits this section makes internally,
so a lock acquired on one pooled connection could end up "released" on a
different one and never actually clear.

Lease safety model (why a stale-lease recovery can never race unsafely,
and never causes a duplicate side effect):

- The claim UPDATE's WHERE clause is `stepping = false OR
  stepping_claimed_at < now() - LEASE_TTL`. Postgres serializes concurrent
  UPDATEs to the same row: only the first one to commit actually changes
  the row (to a fresh `stepping_claim_id` + `stepping_claimed_at = now()`);
  every other concurrent UPDATE -- including other stale-recovery
  attempts racing the same stale lease -- re-evaluates its WHERE clause
  against the post-commit row and no longer matches (the lease is no
  longer stale), so it affects zero rows and the caller gets CONFLICT.
  This is the same CAS pattern the old plain-boolean claim already used;
  only the WHERE clause grew an OR branch for staleness.
- Release only clears the lease if `stepping_claim_id` still matches the
  claim that opened it (`UPDATE ... WHERE stepping_claim_id = :mine`).
  This stops a zombie process -- one whose lease already went stale and
  was recovered by someone else -- from waking up later and clearing a
  *different*, currently-active claim out from under its legitimate
  holder.
- A stale-lease recovery re-enters `_advance()`, which re-derives the
  next action purely from persisted `ExecutionStep` history
  (`_load_history`); if the crashed holder never got as far as a tool
  call, recovery is indistinguishable from an ordinary fresh step(). If
  the crashed holder's tool call *did* fire before it died, safety then
  depends on that tool being idempotent -- refund_payment already is
  (unique `idempotency_key`); deploy_staging/deploy_production are made
  idempotent the same way (see tools/devops.py), so a recovered step that
  re-executes a tool call whose side effect already landed replays the
  existing result instead of creating a duplicate.

Forward progress is additionally recorded via an INSERT into
execution_steps under a UNIQUE(execution_id, sequence) constraint, the
same pattern audit_events uses.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
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

# Execution steps bounded per Milestone 10: a planner bug or a workflow that
# never converges must not spin forever. Configurable via
# MAX_EXECUTION_STEPS; the deterministic demo planner never comes close to
# this in normal operation (every workflow finishes in <=4 steps).
MAX_EXECUTION_STEPS = get_settings().max_execution_steps

# How long a stepping claim is honored before a new caller may treat it as
# abandoned (crashed holder) and safely recover it. See the module
# docstring's "Lease safety model" for the full argument.
LEASE_TTL = timedelta(seconds=get_settings().stepping_lease_ttl_seconds)

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

        claim_id = self._claim_stepping(db, execution)
        if claim_id is None:
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
            self._release_stepping(db, execution_id, claim_id)

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

        claim_id = self._claim_stepping(db, execution)
        if claim_id is None:
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
            self._release_stepping(db, execution_id, claim_id)

    @staticmethod
    def _claim_stepping(db: Session, execution: Execution) -> uuid.UUID | None:
        """Attempts to claim the stepping lease. Returns the new claim id on
        success, or None if someone else holds a still-fresh lease. See the
        module docstring's "Lease safety model" for the full argument."""
        claim_id = uuid.uuid4()
        now = datetime.now(UTC)
        claimed = (
            db.execute(
                update(Execution)
                .where(
                    Execution.id == execution.id,
                    or_(
                        Execution.stepping.is_(False),
                        Execution.stepping_claimed_at < now - LEASE_TTL,
                    ),
                )
                .values(stepping=True, stepping_claim_id=claim_id, stepping_claimed_at=now)
            ).rowcount
            > 0
        )
        db.commit()
        db.refresh(execution)
        return claim_id if claimed else None

    @staticmethod
    def _release_stepping(db: Session, execution_id: uuid.UUID, claim_id: uuid.UUID) -> None:
        # Only clears the lease if it still belongs to this claim -- a
        # zombie holder whose lease already went stale and was recovered by
        # someone else must not be able to clear the new, active claim.
        db.execute(
            update(Execution)
            .where(Execution.id == execution_id, Execution.stepping_claim_id == claim_id)
            .values(stepping=False, stepping_claim_id=None, stepping_claimed_at=None)
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

        # Bounded regardless of planner behavior: a buggy or non-converging
        # planner must not be able to spin an execution forever. Checked
        # before the planner is even called -- an execution that already
        # has MAX_EXECUTION_STEPS steps fails closed without producing one
        # more.
        if len(history) >= MAX_EXECUTION_STEPS:
            step = self._claim_step(
                db,
                execution.id,
                StepType.FINAL,
                {
                    "decision": "FAIL",
                    "reason": "Execution exceeded MAX_EXECUTION_STEPS",
                    "code": "MAX_STEPS_EXCEEDED",
                },
            )
            if step is None:
                return self._conflict_result(execution)
            self._finalize(
                db,
                execution,
                step,
                StepStatus.FAILED,
                {"reason": "Execution exceeded MAX_EXECUTION_STEPS", "code": "MAX_STEPS_EXCEEDED"},
                AuditEventType.EXECUTION_FAILED,
                {
                    "step_sequence": step.sequence,
                    "reason": "Execution exceeded MAX_EXECUTION_STEPS",
                    "code": "MAX_STEPS_EXCEEDED",
                },
                terminal_status=ExecutionStatus.FAILED,
            )
            return RuntimeResult(
                status="FAILED",
                execution_status=execution.status.value,
                reason="Execution exceeded MAX_EXECUTION_STEPS",
                step_sequence=step.sequence,
            )

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
            status="NOOP",
            reason="Approval approved but not finished executing yet",
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
            actual_event_type = event_type
            actual_event_metadata = event_metadata
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
                else:
                    # The terminal-status CAS lost: something else (e.g. a
                    # concurrent cancel()) already moved the execution out
                    # of RUNNING, so it never actually became
                    # `terminal_status`. The step itself still genuinely
                    # reached `status` (recorded above) -- only the
                    # execution-level audit event must not claim a status
                    # transition that did not happen. Never rewrite what
                    # already happened; describe reality instead.
                    db.refresh(execution)
                    actual_event_type = AuditEventType.EXECUTION_STATUS_ALREADY_TERMINAL
                    actual_event_metadata = {
                        **event_metadata,
                        "attempted_status": terminal_status.value,
                        "actual_status": execution.status.value,
                    }
            rows.append(
                AuditEvent(
                    execution_id=execution.id,
                    sequence=seq,
                    event_type=actual_event_type,
                    actor="agent-runtime",
                    event_metadata=actual_event_metadata,
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
