"""ExternalActionService: the ONLY place authentication (delegated to
require_scope), scope checks, agent-mapping enforcement, idempotency, and
translation between an externally submitted action and a SafeOps-native
one happen (Milestone 11 section 36). Both the generic REST API
(app/api/integrations.py) and the MCP adapter (integrations/mcp/server.py,
via that same REST API over HTTP) call this exclusively -- neither ever
imports AgentRuntime, ToolGateway, or any tool implementation directly,
and this service itself only ever reaches ToolGateway through
AgentRuntime.submit_external_action(), never any other way.

Crash-recovery / idempotency semantics (see Milestone 11 design report
section 10 for the full argument): the durable checkpoint is the
ExternalActionRequest row, keyed by (operator_id, external_request_id). A
retry that finds an existing row first checks whether a matching
ExecutionStep already recorded an outcome for (execution_id, tool_name) --
if so, the result is derived from that step's already-persisted output
instead of calling AgentRuntime.submit_external_action() again. This is
the same "check history before resubmitting" principle
DeterministicPlanner already relies on (`_attempted()`), applied from the
service layer instead of a planner.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.canonical import hash_external_action_payload
from app.core.metrics import increment_counter
from app.models import (
    Agent,
    AgentToolPermission,
    ApprovalRequest,
    AuditEvent,
    Execution,
    ExecutionStep,
    ExternalActionRequest,
    IntegrationAgentMapping,
    Operator,
    Tool,
)
from app.models.enums import (
    ApprovalStatus,
    AuditEventType,
    ExternalActionStatus,
    PermissionType,
    StepStatus,
    StepType,
)
from app.schemas.external_action import (
    ActionResponse,
    ActionStatusResponse,
    SourceInput,
    SubmitActionRequest,
    ToolDescriptor,
)
from app.services.agent_runtime import AgentRuntime
from app.services.audit import commit_chunk
from app.services.planner import Source
from app.tools import ToolNotFoundError, tool_registry
from app.tools.registry import ToolRegistry

_TERMINAL_STATUSES = {
    ExternalActionStatus.EXECUTED,
    ExternalActionStatus.BLOCKED,
    ExternalActionStatus.FAILED,
}


class ExternalActionError(Exception):
    """Raised for any request-level failure that must translate to a
    specific HTTP status + stable error code (section 40), never a raw
    500 or leaked internal detail."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


class ExternalActionService:
    def __init__(
        self, *, runtime: AgentRuntime | None = None, registry: ToolRegistry | None = None
    ) -> None:
        self.runtime = runtime or AgentRuntime()
        self.registry = registry or tool_registry

    # ------------------------------------------------------------------
    # Tool discovery
    # ------------------------------------------------------------------

    def list_tools(
        self, *, operator: Operator, safeops_agent_id: uuid.UUID, db: Session
    ) -> list[ToolDescriptor]:
        self._require_agent_mapping(operator, safeops_agent_id, db)

        rows = db.execute(
            select(Tool, AgentToolPermission)
            .join(AgentToolPermission, AgentToolPermission.tool_id == Tool.id)
            .where(
                AgentToolPermission.agent_id == safeops_agent_id,
                AgentToolPermission.permission != PermissionType.DENY,
            )
            .order_by(Tool.name)
        ).all()

        descriptors: list[ToolDescriptor] = []
        for tool_row, _permission in rows:
            try:
                tool = self.registry.get(tool_row.name)
            except ToolNotFoundError:
                continue  # a Tool row with no in-process implementation has nothing to discover
            descriptors.append(
                ToolDescriptor(
                    name=tool.name,
                    description=tool.description,
                    input_schema=tool.input_schema.model_json_schema(),
                )
            )
        return descriptors

    # ------------------------------------------------------------------
    # Action submission
    # ------------------------------------------------------------------

    def submit(
        self, *, operator: Operator, request: SubmitActionRequest, db: Session
    ) -> ActionResponse:
        agent = self._require_agent_mapping(operator, request.safeops_agent_id, db)
        sources = self._normalize_sources(request.sources)
        payload_hash = hash_external_action_payload(
            safeops_agent_id=request.safeops_agent_id,
            execution_id=request.execution_id,
            tool_name=request.tool_name,
            arguments=request.arguments,
            objective=request.objective,
        )

        existing = self._find_existing(operator.id, request.external_request_id, db)
        if existing is not None:
            self._check_hash_or_conflict(existing, payload_hash)
            return self._resolve_existing(existing, request, sources, db)

        if request.execution_id is not None:
            execution = db.get(Execution, request.execution_id)
            if execution is None or execution.agent_id != agent.id:
                raise ExternalActionError(
                    404, "UNKNOWN_EXECUTION", "execution not found for this agent"
                )
        else:
            start_result = self.runtime.start_execution(
                agent_id=agent.id,
                objective=request.objective or f"External action: {request.tool_name}",
                db=db,
                context={
                    "integration_type": request.integration_type.value,
                    "external_agent_id": request.external_agent_id,
                },
            )
            execution = db.get(Execution, uuid.UUID(start_result.execution_id))

        ext_request = ExternalActionRequest(
            operator_id=operator.id,
            integration_type=request.integration_type,
            external_request_id=request.external_request_id,
            external_agent_id=request.external_agent_id,
            safeops_agent_id=agent.id,
            execution_id=execution.id,
            tool_name=request.tool_name,
            payload_hash=payload_hash,
            status=ExternalActionStatus.RECEIVED,
        )
        db.add(ext_request)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            existing = self._find_existing(operator.id, request.external_request_id, db)
            if existing is None:
                raise
            self._check_hash_or_conflict(existing, payload_hash)
            return self._resolve_existing(existing, request, sources, db)
        db.refresh(ext_request)

        self._emit_audit(
            execution.id,
            AuditEventType.EXTERNAL_REQUEST_RECEIVED,
            {
                "integration_principal_id": str(operator.id),
                "external_request_id": ext_request.external_request_id,
                "tool_name": ext_request.tool_name,
            },
            db,
        )

        return self._invoke_and_apply(ext_request, request.arguments, sources, db)

    def get_status(
        self, *, operator: Operator, external_request_id: str, db: Session
    ) -> ActionStatusResponse:
        existing = self._find_existing(operator.id, external_request_id, db)
        if existing is None:
            raise ExternalActionError(
                404, "UNKNOWN_ACTION", "no action found for this external_request_id"
            )
        if existing.status == ExternalActionStatus.WAITING_APPROVAL:
            self._reconcile_if_resolved(existing, db)
        return self._to_status_response(existing)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _require_agent_mapping(
        self, operator: Operator, safeops_agent_id: uuid.UUID, db: Session
    ) -> Agent:
        agent = db.get(Agent, safeops_agent_id)
        if agent is None:
            raise ExternalActionError(404, "UNKNOWN_AGENT", "no such SafeOps agent")
        mapping = db.scalar(
            select(IntegrationAgentMapping).where(
                IntegrationAgentMapping.operator_id == operator.id,
                IntegrationAgentMapping.agent_id == safeops_agent_id,
            )
        )
        if mapping is None:
            raise ExternalActionError(
                403,
                "AGENT_MAPPING_DENIED",
                "this integration is not authorized to act as the requested SafeOps agent",
            )
        return agent

    @staticmethod
    def _normalize_sources(sources: list[SourceInput]) -> list[Source]:
        # Every externally supplied source defaults UNTRUSTED, always, in
        # this milestone -- there is deliberately no per-integration
        # trust-upgrade configuration yet (see docs/integrations.md "known
        # limitations"). A caller-declared trust level would let any
        # external agent mark its own injected content as safe, defeating
        # Risk Engine prompt-injection detection; if a future milestone
        # adds an explicit allowlist, it must be integration-configured,
        # never request-declared.
        return [Source(type=s.type, trust="UNTRUSTED", content=s.content) for s in sources]

    @staticmethod
    def _find_existing(
        operator_id: uuid.UUID, external_request_id: str, db: Session
    ) -> ExternalActionRequest | None:
        return db.scalar(
            select(ExternalActionRequest).where(
                ExternalActionRequest.operator_id == operator_id,
                ExternalActionRequest.external_request_id == external_request_id,
            )
        )

    @staticmethod
    def _check_hash_or_conflict(existing: ExternalActionRequest, payload_hash: str) -> None:
        if existing.payload_hash != payload_hash:
            increment_counter("idempotency_conflicts_total")
            raise ExternalActionError(
                409,
                "IDEMPOTENCY_CONFLICT",
                "external_request_id was already used with a different payload",
            )

    def _resolve_existing(
        self,
        existing: ExternalActionRequest,
        request: SubmitActionRequest,
        sources: list[Source],
        db: Session,
    ) -> ActionResponse:
        if existing.status in _TERMINAL_STATUSES:
            return self._to_action_response(existing)

        if existing.status == ExternalActionStatus.WAITING_APPROVAL:
            self._reconcile_if_resolved(existing, db)
            return self._to_action_response(existing)

        # RECEIVED / VALIDATED / PROCESSING: has the underlying tool call
        # actually already run (a crash between the gateway call returning
        # and this row being updated), or has nothing happened yet?
        step = self._find_matching_step(existing, db)
        if step is not None:
            self._sync_from_step(existing, step, db)
            return self._to_action_response(existing)

        # Nothing recorded yet -- safe to submit for the first time, using
        # this retry's payload (already hash-confirmed identical to the
        # original).
        return self._invoke_and_apply(existing, request.arguments, sources, db)

    def _invoke_and_apply(
        self,
        ext_request: ExternalActionRequest,
        arguments: dict[str, Any],
        sources: list[Source],
        db: Session,
    ) -> ActionResponse:
        ext_request.status = ExternalActionStatus.PROCESSING
        db.commit()

        runtime_result = self.runtime.submit_external_action(
            execution_id=ext_request.execution_id,
            tool_name=ext_request.tool_name,
            arguments=arguments,
            reason=f"External action via {ext_request.integration_type.value} integration",
            sources=sources,
            db=db,
        )

        if runtime_result.status == "EXECUTED":
            ext_request.status = ExternalActionStatus.EXECUTED
        elif runtime_result.status == "WAITING_APPROVAL":
            ext_request.status = ExternalActionStatus.WAITING_APPROVAL
            if runtime_result.approval_request_id:
                ext_request.approval_request_id = uuid.UUID(runtime_result.approval_request_id)
        elif runtime_result.status == "BLOCKED":
            ext_request.status = ExternalActionStatus.BLOCKED
            ext_request.error_code = "ACTION_BLOCKED"
        elif runtime_result.status == "FAILED":
            ext_request.status = ExternalActionStatus.FAILED
            ext_request.error_code = "TOOL_EXECUTION_FAILED"
        else:
            # NOOP / CONFLICT / NOT_FOUND: something else is concurrently
            # working this execution (e.g. the stepping lease is held by a
            # racing caller). Leave status at PROCESSING -- a retry with
            # the SAME external_request_id will safely re-check history
            # and either find the real outcome or try again, never
            # duplicate a side effect.
            db.commit()
            raise ExternalActionError(
                503,
                "ACTION_PROCESSING_CONFLICT",
                "this execution is busy; retry with the same external_request_id",
            )

        step = self._find_matching_step(ext_request, db)
        if step is not None:
            ext_request.tool_request_id = step.tool_request_id
            if step.status == StepStatus.COMPLETED and step.output:
                ext_request.result_summary = step.output.get("tool_result")
            if ext_request.status in _TERMINAL_STATUSES:
                ext_request.completed_at = step.completed_at
        db.commit()
        db.refresh(ext_request)

        if ext_request.status in _TERMINAL_STATUSES:
            self._emit_completed_audit(ext_request, db)

        return self._to_action_response(ext_request)

    def _reconcile_if_resolved(self, existing: ExternalActionRequest, db: Session) -> None:
        approval = (
            db.get(ApprovalRequest, existing.approval_request_id)
            if existing.approval_request_id
            else None
        )
        if approval is None or approval.status == ApprovalStatus.PENDING:
            return  # still genuinely waiting -- nothing to reconcile yet

        self.runtime.reconcile_external_step(existing.execution_id, db)
        step = self._find_matching_step(existing, db)
        if step is not None:
            self._sync_from_step(existing, step, db)

    def _sync_from_step(
        self, ext_request: ExternalActionRequest, step: ExecutionStep, db: Session
    ) -> None:
        output = step.output or {}
        ext_request.tool_request_id = step.tool_request_id
        if step.status == StepStatus.COMPLETED:
            ext_request.status = ExternalActionStatus.EXECUTED
            ext_request.result_summary = output.get("tool_result")
        elif step.status == StepStatus.WAITING_APPROVAL:
            ext_request.status = ExternalActionStatus.WAITING_APPROVAL
            approval_id = output.get("approval_request_id")
            if approval_id:
                ext_request.approval_request_id = uuid.UUID(approval_id)
        elif step.status == StepStatus.BLOCKED:
            ext_request.status = ExternalActionStatus.BLOCKED
            ext_request.error_code = "ACTION_BLOCKED"
        elif step.status == StepStatus.FAILED:
            ext_request.status = ExternalActionStatus.FAILED
            ext_request.error_code = "TOOL_EXECUTION_FAILED"
        if ext_request.status in _TERMINAL_STATUSES:
            ext_request.completed_at = step.completed_at
        db.commit()
        db.refresh(ext_request)

        if ext_request.status in _TERMINAL_STATUSES:
            self._emit_completed_audit(ext_request, db)

    @staticmethod
    def _find_matching_step(
        ext_request: ExternalActionRequest, db: Session
    ) -> ExecutionStep | None:
        steps = db.scalars(
            select(ExecutionStep)
            .where(
                ExecutionStep.execution_id == ext_request.execution_id,
                ExecutionStep.step_type == StepType.TOOL_CALL,
            )
            .order_by(ExecutionStep.sequence.desc())
        ).all()
        for step in steps:
            if step.input.get("tool_name") == ext_request.tool_name and step.status != (
                StepStatus.PENDING
            ):
                return step
        return None

    @staticmethod
    def _to_action_response(ext_request: ExternalActionRequest) -> ActionResponse:
        status_map = {
            ExternalActionStatus.EXECUTED: "EXECUTED",
            ExternalActionStatus.WAITING_APPROVAL: "REQUIRES_APPROVAL",
            ExternalActionStatus.BLOCKED: "BLOCKED",
            ExternalActionStatus.FAILED: "FAILED",
        }
        message_map = {
            ExternalActionStatus.EXECUTED: "Action executed.",
            ExternalActionStatus.WAITING_APPROVAL: "Human approval required.",
            ExternalActionStatus.BLOCKED: "Action blocked by SafeOps.",
            ExternalActionStatus.FAILED: "Action failed.",
        }
        return ActionResponse(
            status=status_map.get(ext_request.status, "PROCESSING"),
            code=ext_request.error_code,
            message=message_map.get(ext_request.status, "Action is still processing."),
            external_request_id=ext_request.external_request_id,
            execution_id=ext_request.execution_id,
            approval_request_id=ext_request.approval_request_id,
            result=ext_request.result_summary,
        )

    @staticmethod
    def _to_status_response(ext_request: ExternalActionRequest) -> ActionStatusResponse:
        return ActionStatusResponse(
            external_request_id=ext_request.external_request_id,
            status=ext_request.status,
            execution_id=ext_request.execution_id,
            approval_request_id=ext_request.approval_request_id,
            tool_name=ext_request.tool_name,
            result=ext_request.result_summary,
            error_code=ext_request.error_code,
            created_at=ext_request.created_at,
            completed_at=ext_request.completed_at,
        )

    @staticmethod
    def _emit_audit(
        execution_id: uuid.UUID, event_type: AuditEventType, metadata: dict[str, Any], db: Session
    ) -> None:
        # Deliberately minimal: AgentRuntime's own EXECUTION_STEP_STARTED /
        # EXECUTION_WAITING_APPROVAL / EXECUTION_STEP_COMPLETED events
        # (emitted by submit_external_action -> _run_tool_call_step, the
        # exact same path a planner-driven step uses) already describe
        # what happened at the step level -- these two extra event types
        # only add what AgentRuntime's events cannot know: the external
        # integration principal and its own external_request_id. Avoids
        # the audit-event explosion of mirroring every internal event.
        commit_chunk(
            db,
            execution_id,
            lambda seq: [
                AuditEvent(
                    execution_id=execution_id,
                    sequence=seq,
                    event_type=event_type,
                    actor="external-action-service",
                    event_metadata=metadata,
                )
            ],
        )

    def _emit_completed_audit(self, ext_request: ExternalActionRequest, db: Session) -> None:
        self._emit_audit(
            ext_request.execution_id,
            AuditEventType.EXTERNAL_ACTION_COMPLETED,
            {
                "integration_principal_id": str(ext_request.operator_id),
                "external_request_id": ext_request.external_request_id,
                "tool_name": ext_request.tool_name,
                "outcome": ext_request.status.value,
            },
            db,
        )
