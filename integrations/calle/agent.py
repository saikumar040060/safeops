"""Real CALL-E voice-agent integration for SafeOps.

Security boundary, stated once here (same as every other adapter in
integrations/): this file never imports from `app.*`, never opens a
database connection, and never calls ToolGateway directly. CALL-E places
a real outbound phone call and returns a structured result once it's
done -- that structured result is then submitted to SafeOps as an
external action through the same generic API every other integration
uses (`integrations/shared/client.py` -> `POST /api/integrations/actions`).
Whatever CALL-E's call determines the customer wants still has to pass
Permission -> Policy -> Risk -> Approval before anything happens. CALL-E
itself never executes a SafeOps tool -- it only produces a structured
answer to a question; this code decides what SafeOps action (if any) that
answer maps to, and SafeOps decides whether that action is allowed.

The call transcript / the customer's own words are UNTRUSTED input, same
as a support ticket body -- attached to the SafeOps submission as a
`voice_call_transcript` source, never trusted by default. This is what
lets Risk Engine catch a manipulated or adversarial phone call the same
way it catches a prompt-injected support ticket (see demo_malicious.py).

Configuration (environment variables):
  CALLE_API_KEY                from the CALL-E dashboard
  CALLE_RECIPIENT_PHONE        E.164 phone number to call, e.g. +15551234567
  SAFEOPS_API_BASE_URL         e.g. http://localhost:8000/api
  SAFEOPS_INTEGRATION_TOKEN    bearer token for an INTEGRATION principal
  SAFEOPS_AGENT_ID             the SafeOps agent UUID this integration
                               acts on behalf of (must be mapped via
                               IntegrationAgentMapping)
"""

import os
import sys
import uuid
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))

from calle import CalleClient
from client import SafeOpsAPIError, SafeOpsClient, Source  # noqa: E402

REFUND_TASK = (
    "You are calling on behalf of SafeOps customer support to confirm a "
    "pending $750.00 refund for a duplicate payment (PAY-9003) on customer "
    "CUST-1001's account. Politely explain the situation and ask whether "
    "they would like to proceed with the refund. Record whatever they say "
    "verbatim."
)

REFUND_RESULT_SCHEMA = {
    "type": "object",
    "required": ["wants_refund", "customer_statement"],
    "properties": {
        "wants_refund": {
            "type": "boolean",
            "description": "Whether the customer confirmed they want the refund.",
        },
        "confirmed_amount": {
            "type": "string",
            "description": "The refund amount as stated/confirmed, e.g. '750.00'.",
        },
        "customer_statement": {
            "type": "string",
            "description": "What the customer actually said, as close to verbatim as possible.",
        },
    },
}


def place_refund_confirmation_call(calle_client: CalleClient, phone_number: str) -> dict[str, Any]:
    """Places a REAL outbound phone call via the CALL-E API and blocks
    until it completes. This is the one piece of this integration that
    actually talks to CALL-E; everything downstream only touches SafeOps."""
    return calle_client.calls.create_and_wait(
        task=REFUND_TASK,
        recipient={"phone": phone_number},
        result_schema=REFUND_RESULT_SCHEMA,
        idempotency_key=f"safeops-refund-confirm-{uuid.uuid4()}",
    )


def submit_call_outcome_to_safeops(
    safeops_client: SafeOpsClient, safeops_agent_id: str, call_result: dict[str, Any]
) -> dict[str, Any]:
    """Translates a completed CALL-E call's structured result into (at
    most) one SafeOps action submission. This function is what a
    malicious/manipulated call transcript would have to get past --
    verified independently of a live call by demo_malicious.py."""
    structured = call_result.get("structured_result") or {}
    transcript = structured.get("customer_statement") or ""
    sources = [Source(type="voice_call_transcript", content=transcript)] if transcript else None

    if not structured.get("wants_refund"):
        return {
            "status": "NO_ACTION",
            "message": "Customer did not confirm the refund; no SafeOps action submitted.",
        }

    try:
        return safeops_client.submit_action(
            external_request_id=str(uuid.uuid4()),
            safeops_agent_id=safeops_agent_id,
            tool_name="refund_payment",
            arguments={
                "payment_id": "PAY-9003",
                "amount": structured.get("confirmed_amount") or "750.00",
                "reason": "Refund confirmed by customer via CALL-E voice call",
                "idempotency_key": f"calle-refund-{uuid.uuid4()}",
            },
            objective="CALL-E voice-confirmed refund",
            sources=sources,
        )
    except SafeOpsAPIError as exc:
        return {"status": "ERROR", "code": exc.code, "message": exc.message}


def build_calle_client() -> CalleClient:
    return CalleClient(api_key=os.environ["CALLE_API_KEY"])


def build_safeops_client() -> SafeOpsClient:
    base_url = os.environ.get("SAFEOPS_API_BASE_URL", "http://localhost:8000/api")
    return SafeOpsClient(base_url, os.environ["SAFEOPS_INTEGRATION_TOKEN"])


if __name__ == "__main__":
    phone = os.environ["CALLE_RECIPIENT_PHONE"]
    agent_id = os.environ["SAFEOPS_AGENT_ID"]

    calle_client = build_calle_client()
    safeops_client = build_safeops_client()

    print(f"Placing a real CALL-E call to {phone} ...")
    call_result = place_refund_confirmation_call(calle_client, phone)
    print("CALL-E call finished:", call_result.get("status"))
    print("Structured result:", call_result.get("structured_result"))

    outcome = submit_call_outcome_to_safeops(safeops_client, agent_id, call_result)
    print("SafeOps outcome:", outcome)
