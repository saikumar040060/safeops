"""Deterministic risk signal detectors. Each function inspects a fixed,
pre-built `DetectionInput` and returns a `SignalMatch` or None. No detector
here ever executes, evaluates, or dynamically imports anything derived from
tool arguments or source content -- every check is a plain, case-insensitive
substring or fixed-pattern match against a constant list from
`risk_config.py`.
"""

import re
import uuid
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ToolRequest
from app.services import risk_config as cfg


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


@dataclass
class SignalMatch:
    signal: str
    reason_code: str
    indicator: str


@dataclass
class DetectionInput:
    tool_name: str
    arguments: dict[str, Any]
    objective: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    execution_id: uuid.UUID | None = None
    db: Session | None = None

    def untrusted_text(self) -> list[str]:
        texts = []
        for source in self.sources:
            if not isinstance(source, dict):
                continue
            # Fail closed: a source with no explicit trust label is treated
            # as untrusted, never as implicitly safe.
            trust = str(source.get("trust", "UNTRUSTED")).upper()
            content = source.get("content")
            if trust != "TRUSTED" and isinstance(content, str):
                texts.append(_normalize(content))
        return texts

    def argument_text(self) -> str:
        parts = [str(v) for v in self.arguments.values() if isinstance(v, str)]
        return _normalize(" ".join(parts))


def detect_prompt_injection(inp: DetectionInput) -> SignalMatch | None:
    for text in inp.untrusted_text():
        for phrase in cfg.PROMPT_INJECTION_PHRASES:
            if phrase in text:
                return SignalMatch("PROMPT_INJECTION", "INJECTION_PHRASE_MATCH", phrase)
    return None


def detect_privilege_escalation(inp: DetectionInput) -> SignalMatch | None:
    for text in inp.untrusted_text():
        for phrase in cfg.PRIVILEGE_ESCALATION_PHRASES:
            if phrase in text:
                return SignalMatch("PRIVILEGE_ESCALATION", "ESCALATION_PHRASE_MATCH", phrase)
    return None


def detect_data_exfiltration(inp: DetectionInput) -> SignalMatch | None:
    if inp.tool_name in cfg.DATA_EXPORT_TOOLS:
        return SignalMatch("DATA_EXFILTRATION", "DATA_EXPORT_TOOL", inp.tool_name)
    for text in inp.untrusted_text():
        for phrase in cfg.DATA_EXFILTRATION_PHRASES:
            if phrase in text:
                return SignalMatch("DATA_EXFILTRATION", "EXFILTRATION_PHRASE_MATCH", phrase)
    return None


def detect_scope_deviation(inp: DetectionInput) -> SignalMatch | None:
    category = cfg.TOOL_CATEGORIES.get(inp.tool_name)
    if category is None:
        return None
    objective_text = _normalize(inp.objective)
    implied_categories = {
        cat
        for cat, keywords in cfg.OBJECTIVE_CATEGORY_KEYWORDS.items()
        if any(keyword in objective_text for keyword in keywords)
    }
    if not implied_categories:
        return None
    if category not in implied_categories:
        return SignalMatch(
            "SCOPE_DEVIATION",
            "TOOL_OUTSIDE_OBJECTIVE_SCOPE",
            f"{inp.tool_name} not in {sorted(implied_categories)}",
        )
    return None


def detect_financial_risk(inp: DetectionInput) -> SignalMatch | None:
    if inp.tool_name != "refund_payment":
        return None
    raw_amount = inp.arguments.get("amount")
    if raw_amount is None:
        return None
    try:
        amount = Decimal(str(raw_amount))
    except (InvalidOperation, ValueError, TypeError):
        return None
    for threshold, _weight in cfg.FINANCIAL_RISK_BANDS:
        if amount <= threshold:
            return SignalMatch("FINANCIAL_RISK", f"AMOUNT_LTE_{threshold}", str(amount))
    return SignalMatch("FINANCIAL_RISK", "AMOUNT_ABOVE_MAX_BAND", str(amount))


def financial_risk_weight(inp: DetectionInput) -> int:
    if inp.tool_name != "refund_payment":
        return 0
    raw_amount = inp.arguments.get("amount")
    if raw_amount is None:
        return 0
    try:
        amount = Decimal(str(raw_amount))
    except (InvalidOperation, ValueError, TypeError):
        return 0
    for threshold, weight in cfg.FINANCIAL_RISK_BANDS:
        if amount <= threshold:
            return weight
    return cfg.FINANCIAL_RISK_ABOVE_MAX


def detect_sensitive_data_access(inp: DetectionInput) -> SignalMatch | None:
    haystacks = [inp.argument_text(), *inp.untrusted_text()]
    for text in haystacks:
        for keyword in cfg.SENSITIVE_DATA_KEYWORDS:
            if keyword in text:
                return SignalMatch("SENSITIVE_DATA_ACCESS", "SENSITIVE_KEYWORD_MATCH", keyword)
    return None


def detect_destructive_action(inp: DetectionInput) -> SignalMatch | None:
    haystack = _normalize(inp.tool_name.replace("_", " "))
    for keyword in cfg.DESTRUCTIVE_ACTION_KEYWORDS:
        if keyword in haystack:
            return SignalMatch("DESTRUCTIVE_ACTION", "DESTRUCTIVE_KEYWORD_MATCH", keyword)
    return None


def detect_external_communication(inp: DetectionInput) -> SignalMatch | None:
    if inp.tool_name in cfg.EXTERNAL_COMMUNICATION_TOOLS:
        return SignalMatch("EXTERNAL_COMMUNICATION", "EXTERNAL_COMMUNICATION_TOOL", inp.tool_name)
    if re.search(cfg.EMAIL_LIKE_PATTERN, inp.argument_text()):
        return SignalMatch("EXTERNAL_COMMUNICATION", "EMAIL_LIKE_ARGUMENT", "argument")
    haystack = _normalize(inp.tool_name.replace("_", " "))
    for keyword in cfg.EXTERNAL_COMMUNICATION_KEYWORDS:
        if keyword in haystack:
            return SignalMatch("EXTERNAL_COMMUNICATION", "EXTERNAL_KEYWORD_MATCH", keyword)
    return None


def detect_unusual_tool_sequence(inp: DetectionInput) -> SignalMatch | None:
    if cfg.TOOL_CATEGORIES.get(inp.tool_name) != "data_export":
        return None
    if inp.db is None or inp.execution_id is None:
        return None
    prior_read = inp.db.scalar(
        select(ToolRequest.id)
        .where(
            ToolRequest.execution_id == inp.execution_id,
            ToolRequest.tool_name.in_(cfg.CUSTOMER_DATA_READ_TOOLS),
        )
        .limit(1)
    )
    if prior_read is not None:
        return SignalMatch("UNUSUAL_TOOL_SEQUENCE", "READ_THEN_EXPORT_SEQUENCE", inp.tool_name)
    return None


DETECTORS = (
    detect_prompt_injection,
    detect_privilege_escalation,
    detect_data_exfiltration,
    detect_scope_deviation,
    detect_financial_risk,
    detect_sensitive_data_access,
    detect_destructive_action,
    detect_external_communication,
    detect_unusual_tool_sequence,
)
