"""Structured planner interface and a deterministic demo planner.

The planner never touches a tool, a database session, or ToolGateway. It is
a pure function of (execution, context, history) that returns one of three
fixed, Pydantic-validated shapes -- there is no free-form function
invocation, no code execution, and no path by which a planner's return
value can become anything other than a validated tool-name/argument pair.
This boundary is what lets AgentRuntime later swap in an LLM planner
without changing the security boundary: whatever the planner proposes,
AgentRuntime still only ever calls ToolGateway.execute() with it.
"""

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

from app.models import Execution, ExecutionStep
from app.models.enums import StepStatus, StepType

EMAIL_PATTERN = re.compile(r"[^\s@]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
CUSTOMER_ID_PATTERN = re.compile(r"CUST-\d+", re.IGNORECASE)
TICKET_ID_PATTERN = re.compile(r"TCK-\d+", re.IGNORECASE)
VERSION_PATTERN = re.compile(r"\d+(?:\.\d+){1,2}(?:-[A-Za-z0-9]+)?")
KNOWN_SERVICES = ("checkout-service",)


class Source(BaseModel):
    type: str
    trust: Literal["TRUSTED", "UNTRUSTED"]
    content: str


class ToolAction(BaseModel):
    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any]
    reason: str = Field(min_length=1)
    sources: list[Source] = Field(default_factory=list)


class Complete(BaseModel):
    reason: str = Field(min_length=1)


class Fail(BaseModel):
    reason: str = Field(min_length=1)
    code: str = "PLANNER_FAILURE"


PlannerDecision = ToolAction | Complete | Fail


class Planner(Protocol):
    def next_action(
        self, execution: Execution, context: dict[str, Any], history: list[ExecutionStep]
    ) -> PlannerDecision: ...


def _completed_step(history: list[ExecutionStep], tool_name: str) -> ExecutionStep | None:
    for step in history:
        if (
            step.step_type == StepType.TOOL_CALL
            and step.status == StepStatus.COMPLETED
            and step.input.get("tool_name") == tool_name
        ):
            return step
    return None


def _attempted(history: list[ExecutionStep], tool_name: str) -> ExecutionStep | None:
    for step in history:
        if step.step_type == StepType.TOOL_CALL and step.input.get("tool_name") == tool_name:
            return step
    return None


def _tool_result(step: ExecutionStep) -> dict[str, Any]:
    output = step.output or {}
    return output.get("tool_result") or {}


def _find_duplicate_payment(payments: list[dict[str, Any]]) -> dict[str, Any] | None:
    by_amount: dict[str, list[dict[str, Any]]] = {}
    for payment in payments:
        try:
            key = str(Decimal(str(payment.get("amount"))))
        except (InvalidOperation, ValueError, TypeError):
            continue
        by_amount.setdefault(key, []).append(payment)

    for group in by_amount.values():
        if len(group) < 2:
            continue
        for payment in group:
            if payment.get("status") == "SUCCEEDED":
                return payment
    return None


class DeterministicPlanner:
    """Demo-only planner: fixed, keyword-driven workflows, no LLM, no
    hidden state -- every decision is re-derived from `history` each call
    so it is safe to call repeatedly and safe to resume from any point.
    """

    def next_action(
        self, execution: Execution, context: dict[str, Any], history: list[ExecutionStep]
    ) -> PlannerDecision:
        objective = execution.objective
        objective_lower = objective.lower()

        ticket_match = TICKET_ID_PATTERN.search(objective)
        if "ticket" in objective_lower and ticket_match:
            return self._support_ticket_workflow(ticket_match.group(0), history)

        customer_match = CUSTOMER_ID_PATTERN.search(objective)
        if "duplicate" in objective_lower and customer_match:
            return self._refund_duplicate_workflow(execution, customer_match.group(0), history)

        if "deploy" in objective_lower:
            return self._deploy_workflow(objective, objective_lower, history)

        return Fail(
            reason="Objective did not match any known deterministic workflow",
            code="UNSUPPORTED_OBJECTIVE",
        )

    @staticmethod
    def _refund_duplicate_workflow(
        execution: Execution, customer_id: str, history: list[ExecutionStep]
    ) -> PlannerDecision:
        if _completed_step(history, "read_customer") is None:
            return ToolAction(
                tool_name="read_customer",
                arguments={"customer_id": customer_id},
                reason="Need customer details to investigate duplicate payment",
            )

        payments_step = _completed_step(history, "get_payments")
        if payments_step is None:
            return ToolAction(
                tool_name="get_payments",
                arguments={"customer_id": customer_id},
                reason="Need payment history to find the duplicate charge",
            )

        if _attempted(history, "refund_payment") is not None:
            return Complete(reason="Refund already attempted for the duplicate payment")

        payments = _tool_result(payments_step).get("payments", [])
        duplicate = _find_duplicate_payment(payments)
        if duplicate is None:
            return Complete(reason="No duplicate payment found for this customer")

        return ToolAction(
            tool_name="refund_payment",
            arguments={
                "payment_id": duplicate["payment_id"],
                "amount": duplicate["amount"],
                "reason": "duplicate payment",
                "idempotency_key": f"runtime-{execution.id}-refund",
            },
            reason=f"Refunding duplicate payment {duplicate['payment_id']}",
        )

    @staticmethod
    def _support_ticket_workflow(
        ticket_id: str, history: list[ExecutionStep]
    ) -> PlannerDecision:
        ticket_step = _completed_step(history, "get_support_ticket")
        if ticket_step is None:
            return ToolAction(
                tool_name="get_support_ticket",
                arguments={"ticket_id": ticket_id},
                reason=f"Need to read ticket {ticket_id} to investigate it",
            )

        if _attempted(history, "send_external_email") is not None:
            return Complete(reason="Ticket-driven action already attempted")

        body = _tool_result(ticket_step).get("body", "")
        email_match = EMAIL_PATTERN.search(body)
        if email_match is None:
            # A naive planner has nothing that looks like an external-send
            # instruction to literally follow -- an ordinary ticket (e.g.
            # "please refund my duplicate charge") just gets read and
            # closed out here. This is content-shape detection, not a
            # security judgment: it only decides what a naive planner
            # would literally try next, never whether it's safe.
            return Complete(reason=f"Ticket {ticket_id} reviewed, no further action needed")

        # This is deliberately naive: a demo planner with no security
        # judgment of its own, echoing an instruction embedded in untrusted
        # ticket content. The untrusted body is passed through as a tagged
        # Source rather than merged into the action -- SafeOps's Risk
        # Engine, not planner judgment, is what has to stop this.
        return ToolAction(
            tool_name="send_external_email",
            arguments={
                "to": email_match.group(0),
                "subject": f"Re: {ticket_id}",
                "body": "Data requested by the ticket.",
            },
            reason=f"Ticket {ticket_id} asked for this data to be sent externally",
            sources=[Source(type="support_ticket", trust="UNTRUSTED", content=body)],
        )

    @staticmethod
    def _deploy_workflow(
        objective: str, objective_lower: str, history: list[ExecutionStep]
    ) -> PlannerDecision:
        service_name = next((s for s in KNOWN_SERVICES if s in objective_lower), None)
        version_match = VERSION_PATTERN.search(objective)
        if service_name is None or version_match is None:
            return Fail(
                reason="Could not determine service name or version from objective",
                code="UNSUPPORTED_OBJECTIVE",
            )
        version = version_match.group(0)
        target_tool = "deploy_production" if "production" in objective_lower else "deploy_staging"

        if _completed_step(history, "get_deployment") is None:
            return ToolAction(
                tool_name="get_deployment",
                arguments={"service_name": service_name},
                reason=f"Need current deployment state for {service_name}",
            )

        if _attempted(history, target_tool) is not None:
            return Complete(reason=f"Deploy of {service_name} {version} already attempted")

        environment = "production" if target_tool == "deploy_production" else "staging"
        return ToolAction(
            tool_name=target_tool,
            arguments={"service_name": service_name, "version": version},
            reason=f"Deploy {service_name} {version} to {environment}",
        )
