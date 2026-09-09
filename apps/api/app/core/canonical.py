"""Canonical serialization + hashing for external-action idempotency
(Milestone 11). Deliberately not ad-hoc string concatenation: a single
`json.dumps(..., sort_keys=True)` pass is a well-defined, order-independent
serialization of any JSON-safe structure, so two logically-identical
payloads (same keys, same values, submitted with different dict ordering)
always hash the same, and any real difference always hashes differently.
"""

import hashlib
import json
import uuid
from typing import Any


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def hash_external_action_payload(
    *,
    safeops_agent_id: uuid.UUID,
    execution_id: uuid.UUID | None,
    tool_name: str,
    arguments: dict[str, Any],
    objective: str | None,
) -> str:
    """Deterministic per logical action. Deliberately excludes: timestamps
    (volatile by nature), external_request_id (that is the lookup key
    itself, not part of what it identifies), and any other request
    metadata that does not change what SafeOps would actually do."""
    canonical = {
        "safeops_agent_id": str(safeops_agent_id),
        "execution_id": str(execution_id) if execution_id else None,
        "tool_name": tool_name,
        "arguments": arguments,
        "objective": objective,
    }
    return hashlib.sha256(canonical_json(canonical).encode("utf-8")).hexdigest()
