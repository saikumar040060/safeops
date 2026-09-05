"""Deterministic Risk Engine. No LLM, heuristic model, or ML anomaly
detector ever participates in the final ALLOW/REQUIRE_APPROVAL/BLOCK
decision -- every signal is a fixed, explainable rule over a small set of
deterministic detectors (`risk_signals.py`) and constants (`risk_config.py`).

Any failure while assessing (a broken detector, malformed context) fails
closed to BLOCK rather than silently defaulting to ALLOW -- see
`RiskEngine.assess()`.
"""

from typing import Any

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models import Agent, Execution, Tool
from app.models.enums import PolicyAction, RiskLevel
from app.services import risk_config as cfg
from app.services.risk_signals import DETECTORS, DetectionInput, financial_risk_weight

_SEVERITY_ORDER = {PolicyAction.ALLOW: 0, PolicyAction.REQUIRE_APPROVAL: 1, PolicyAction.BLOCK: 2}

# Signal combinations that force BLOCK regardless of the numeric score.
_HARD_BLOCK_PAIRS: list[set[str]] = [{"PROMPT_INJECTION", "DATA_EXFILTRATION"}]
_HARD_BLOCK_SINGLE: set[str] = {"PRIVILEGE_ESCALATION"}


def combine_decisions(
    policy_decision: PolicyAction, risk_recommendation: PolicyAction
) -> PolicyAction:
    """Risk may only preserve or escalate; it can never downgrade a decision."""
    return max(policy_decision, risk_recommendation, key=lambda d: _SEVERITY_ORDER[d])


def _risk_level_for_score(score: int) -> RiskLevel:
    for ceiling, level in cfg.RISK_LEVEL_BANDS:
        if score <= ceiling:
            return RiskLevel(level)
    return RiskLevel.CRITICAL  # pragma: no cover - bands cover 0-100 fully


def _recommended_action_for(score: int, level: RiskLevel) -> PolicyAction:
    if level == RiskLevel.LOW:
        return PolicyAction.ALLOW
    if level == RiskLevel.MEDIUM:
        if score >= cfg.MEDIUM_REQUIRE_APPROVAL_THRESHOLD:
            return PolicyAction.REQUIRE_APPROVAL
        return PolicyAction.ALLOW
    if level == RiskLevel.HIGH:
        return PolicyAction.REQUIRE_APPROVAL
    return PolicyAction.BLOCK  # CRITICAL


class RiskAssessmentResult(BaseModel):
    risk_score: int
    risk_level: RiskLevel
    signals: list[str]
    reason_codes: list[str]
    recommended_action: PolicyAction
    context: dict[str, Any]


class RiskEngine:
    def assess(
        self,
        *,
        agent: Agent,
        execution: Execution,
        tool: Tool,
        arguments: dict[str, Any],
        policy_decision: Any,
        context: dict[str, Any] | None,
        db: Session,
    ) -> RiskAssessmentResult:
        safe_context = context if isinstance(context, dict) else {}
        raw_sources = safe_context.get("sources")
        sources = raw_sources if isinstance(raw_sources, list) else []

        det_input = DetectionInput(
            tool_name=tool.name,
            arguments=arguments,
            objective=execution.objective,
            sources=sources,
            execution_id=execution.id,
            db=db,
        )

        signals: list[str] = []
        reason_codes: list[str] = []
        indicators: dict[str, str] = {}
        score = 0
        assessment_failed = False

        for detector in DETECTORS:
            try:
                match = detector(det_input)
            except Exception:
                # A single broken/malformed detector must not silently
                # vanish -- it forces the whole assessment to fail closed
                # below, but other detectors still get a chance to run so
                # we don't lose real signals they did find.
                assessment_failed = True
                continue

            if match is None:
                continue
            signals.append(match.signal)
            reason_codes.append(match.reason_code)
            indicators[match.signal] = match.indicator
            if match.signal == "FINANCIAL_RISK":
                score += financial_risk_weight(det_input)
            else:
                score += cfg.SIGNAL_WEIGHTS.get(match.signal, 0)

        score = max(0, min(100, score))
        level = _risk_level_for_score(score)
        recommended_action = _recommended_action_for(score, level)

        signal_set = set(signals)
        if any(pair.issubset(signal_set) for pair in _HARD_BLOCK_PAIRS):
            recommended_action = PolicyAction.BLOCK
            score = max(score, 100)
            level = RiskLevel.CRITICAL
        if signal_set & _HARD_BLOCK_SINGLE:
            recommended_action = PolicyAction.BLOCK
            score = max(score, 100)
            level = RiskLevel.CRITICAL

        if assessment_failed:
            recommended_action = PolicyAction.BLOCK
            score = 100
            level = RiskLevel.CRITICAL
            reason_codes.append("RISK_ASSESSMENT_ERROR")

        return RiskAssessmentResult(
            risk_score=score,
            risk_level=level,
            signals=signals,
            reason_codes=reason_codes,
            recommended_action=recommended_action,
            context={
                "tool_name": tool.name,
                "agent_id": str(agent.id),
                "indicators": indicators,
            },
        )


risk_engine = RiskEngine()
