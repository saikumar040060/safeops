"""Single source of truth for Risk Engine weights, keyword lists, and
tool-category mappings. No code execution of any kind reads from here --
every list below is a fixed, developer-authored constant, never
user-controlled input.
"""

from decimal import Decimal

SIGNAL_WEIGHTS: dict[str, int] = {
    "PROMPT_INJECTION": 60,
    "DATA_EXFILTRATION": 50,
    "PRIVILEGE_ESCALATION": 50,
    "DESTRUCTIVE_ACTION": 40,
    "SENSITIVE_DATA_ACCESS": 35,
    "SCOPE_DEVIATION": 35,
    "EXTERNAL_COMMUNICATION": 20,
    "UNUSUAL_TOOL_SEQUENCE": 20,
}

# FINANCIAL_RISK is amount-dependent rather than a fixed weight; thresholds
# mirror the Milestone 5 refund policy bands for a consistent story, but are
# an independent, purely-additive risk signal.
FINANCIAL_RISK_BANDS: list[tuple[Decimal, int]] = [
    (Decimal("100"), 10),
    (Decimal("1000"), 25),
]
FINANCIAL_RISK_ABOVE_MAX = 40

RISK_LEVEL_BANDS: list[tuple[int, str]] = [
    (29, "LOW"),
    (59, "MEDIUM"),
    (84, "HIGH"),
    (100, "CRITICAL"),
]

# Within the MEDIUM band, scores at or above this still-in-band threshold
# recommend REQUIRE_APPROVAL rather than ALLOW.
MEDIUM_REQUIRE_APPROVAL_THRESHOLD = 45

# Phrases that indicate an attempt to manipulate the agent via untrusted
# content. Case-insensitive substring match only -- no regex, no eval/exec.
PROMPT_INJECTION_PHRASES: list[str] = [
    "ignore previous instructions",
    "ignore all previous instructions",
    "reveal credentials",
    "reveal secrets",
    "export the database",
    "export the entire customer database",
    "send customer data to",
    "upload data to",
    "do not tell the user",
]

# A distinct, escalation-flavored subset of the same style of phrase.
PRIVILEGE_ESCALATION_PHRASES: list[str] = [
    "bypass security",
    "disable safeguards",
    "override policy",
    "act as administrator",
]

# Phrases that, on their own, describe bulk data exfiltration intent
# regardless of whether they came from an injection attempt.
DATA_EXFILTRATION_PHRASES: list[str] = [
    "export the database",
    "export the entire customer database",
    "send customer data to",
    "upload data to",
]

SENSITIVE_DATA_KEYWORDS: list[str] = [
    "password",
    "api key",
    "api_key",
    "token",
    "secret",
    "ssn",
    "private key",
    "credential",
]

DESTRUCTIVE_ACTION_KEYWORDS: list[str] = [
    "delete",
    "drop",
    "destroy",
    "terminate",
    "revoke",
]

EXTERNAL_COMMUNICATION_KEYWORDS: list[str] = [
    "email",
    "send",
    "upload",
]

# Tools whose entire purpose is moving data/communication outside the system.
# Used for DATA_EXFILTRATION / EXTERNAL_COMMUNICATION / scope-category checks.
DATA_EXPORT_TOOLS: set[str] = {"export_customer_data", "send_external_email"}
EXTERNAL_COMMUNICATION_TOOLS: set[str] = {"send_external_email"}

# Coarse tool categories for the deterministic SCOPE_DEVIATION heuristic.
TOOL_CATEGORIES: dict[str, str] = {
    "read_customer": "customer_support",
    "get_payments": "customer_support",
    "refund_payment": "customer_support",
    "get_support_ticket": "customer_support",
    "read_logs": "devops",
    "get_deployment": "devops",
    "deploy_staging": "devops",
    "deploy_production": "devops",
    "export_customer_data": "data_export",
    "send_external_email": "data_export",
}

# Keywords in an Execution.objective that imply which category of tool call
# is in scope. Checked as case-insensitive substrings.
OBJECTIVE_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "customer_support": ["customer", "payment", "refund", "duplicate", "ticket", "support"],
    "devops": ["deploy", "production", "incident", "service", "staging", "outage"],
}

# Data-reading tools that, if seen earlier in the same execution, make a
# later data_export-category call look like a read-then-exfiltrate sequence.
CUSTOMER_DATA_READ_TOOLS: set[str] = {"read_customer", "get_payments", "get_support_ticket"}

# A fixed, non-user-controlled pattern for spotting an email-like value in
# tool arguments -- not compiled from any request-supplied string.
EMAIL_LIKE_PATTERN = r"[^\s@]+@[^\s@]+\.[^\s@]+"
