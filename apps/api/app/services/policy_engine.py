"""Deterministic Policy Engine.

Evaluates enabled Policy rows for a given (agent, tool, arguments) and
returns a structured ALLOW / REQUIRE_APPROVAL / BLOCK decision. This is
pure, read-only, rule-based evaluation: no LLM, no heuristics, and no
arbitrary code execution ever participates in the decision. The engine
never persists anything -- PolicyDecision persistence is the Tool
Gateway's responsibility, so evaluation stays side-effect free.

Precedence (most specific wins):
    1. policies pinned to this exact agent_id
    2. policies scoped to this agent's agent_type
    3. tool-only policies (no agent_id, no agent_type)
Ranks are tried in that order. A rank is only decisive once at least one
of its enabled policies' conditions actually matches this call; if a
rank has enabled policies but none of them match, evaluation falls
through to the next rank (a narrow agent-specific override that doesn't
apply to this call shouldn't hide a broader policy that does). Within a
decisive rank, only policies whose conditions evaluate true are
candidates; the highest `priority` wins. A tie among top-priority
candidates with different actions fails closed as POLICY_CONFLICT
without falling through -- that rank did apply, just ambiguously. No
rank ever matches: fails closed as NO_MATCHING_POLICY.
"""

import uuid
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Agent, Execution, Policy, Tool
from app.models.enums import PolicyAction
from app.services.policy_conditions import PolicyConditionError, evaluate_conditions


class PolicyEvaluationResult(BaseModel):
    decision: PolicyAction
    reason: str
    matched_policy: str | None = None
    policy_id: uuid.UUID | None = None
    context: dict[str, Any] = {}


class PolicyEngine:
    def evaluate(
        self,
        *,
        agent: Agent,
        tool: Tool,
        arguments: dict[str, Any],
        execution: Execution,
        db: Session,
    ) -> PolicyEvaluationResult:
        context: dict[str, Any] = {
            "arguments": arguments,
            "agent": {"id": str(agent.id), "type": agent.type, "name": agent.name},
            "tool": {"id": str(tool.id), "name": tool.name},
            "execution": {"id": str(execution.id)},
        }

        candidates = list(
            db.scalars(
                select(Policy).where(Policy.tool_id == tool.id, Policy.enabled.is_(True))
            )
        )

        rank1 = [p for p in candidates if p.agent_id == agent.id]
        rank2 = [p for p in candidates if p.agent_id is None and p.agent_type == agent.type]
        rank3 = [p for p in candidates if p.agent_id is None and p.agent_type is None]

        for rank in (rank1, rank2, rank3):
            if not rank:
                continue
            result = self._resolve_rank(rank, context)
            if result is not None:
                return result

        return PolicyEvaluationResult(
            decision=PolicyAction.BLOCK,
            reason="NO_MATCHING_POLICY: no policy is configured for this agent/tool",
            context=context,
        )

    @staticmethod
    def _resolve_rank(
        policies: list[Policy], context: dict[str, Any]
    ) -> PolicyEvaluationResult | None:
        """Resolve one precedence rank, or return None to fall through to the next."""
        matched: list[Policy] = []
        for policy in policies:
            try:
                if evaluate_conditions(policy.conditions, context):
                    matched.append(policy)
            except PolicyConditionError:
                return PolicyEvaluationResult(
                    decision=PolicyAction.BLOCK,
                    reason="POLICY_EVALUATION_ERROR: invalid policy condition",
                    context=context,
                )

        if not matched:
            return None  # nothing in this rank applies: try the next, broader rank

        top_priority = max(p.priority for p in matched)
        top = [p for p in matched if p.priority == top_priority]

        if len({p.action for p in top}) > 1:
            return PolicyEvaluationResult(
                decision=PolicyAction.BLOCK,
                reason=(
                    "POLICY_CONFLICT: multiple policies matched with equal priority "
                    "and differing actions"
                ),
                context=context,
            )

        chosen = sorted(top, key=lambda p: p.policy_key)[0]
        return PolicyEvaluationResult(
            decision=chosen.action,
            reason=f"Matched policy '{chosen.policy_key}'",
            matched_policy=chosen.policy_key,
            policy_id=chosen.id,
            context=context,
        )


policy_engine = PolicyEngine()
