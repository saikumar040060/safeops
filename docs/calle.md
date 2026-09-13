# CALL-E Adapter

## The rule, stated once

**External agents never execute tools directly. All actions pass through
the SafeOps ToolGateway.**

`integrations/calle/agent.py` uses the real [CALL-E](https://www.heycall-e.com/)
Python SDK (`calle-ai` on PyPI) to place an outbound phone call and get a
structured result back once it completes. CALL-E itself never executes a
SafeOps tool -- it only answers a question by having a real conversation.
This code decides what SafeOps action (if any) that answer maps to, and
submits it through the same generic integration API every other adapter
uses (`integrations/shared/client.py`). Whatever the call determines the
customer wants still has to pass Permission -> Policy -> Risk -> Approval
before anything happens.

## Why this maps CALL-E's outbound-call model onto the requested inbound
## "customer calls in" scenario

CALL-E's actual API places outbound calls (`client.calls.create(...)`
with a `recipient`), not inbound ones. The demo here uses that
capability the other way around: SafeOps places the call to confirm what
a customer wants, rather than the customer calling in. The security
property being demonstrated -- a voice-driven action is still gated by
SafeOps, and a manipulated/adversarial voice transcript is still caught
by Risk Engine -- is the same either direction.

## Configuration

```
CALLE_API_KEY               from the CALL-E dashboard
CALLE_RECIPIENT_PHONE       E.164 number to call, e.g. +15551234567
SAFEOPS_API_BASE_URL        e.g. http://localhost:8000/api
SAFEOPS_INTEGRATION_TOKEN   bearer token for an INTEGRATION principal
SAFEOPS_AGENT_ID            the SafeOps agent UUID this integration acts
                            for (must be mapped via IntegrationAgentMapping)
CALLE_PAYMENT_ID            payment to confirm/refund, default PAY-9003
CALLE_CUSTOMER_ID           customer on that payment, default CUST-1001
CALLE_REFUND_AMOUNT         default confirmed amount, default 750.00
```

`CALLE_API_KEY` can also be replaced with the official CALL-E CLI's
browser OAuth flow (`calle auth login`) if you'd rather not manage a raw
API key -- this was in fact how the live verification below was run.

## Demo 1 -- real live call, refund confirmation

```bash
pip install -r integrations/calle/requirements.txt
python integrations/calle/agent.py
```

Places a real call to `CALLE_RECIPIENT_PHONE` asking the person to
confirm a $750 refund for a duplicate payment (`PAY-9003`). Once CALL-E
returns the structured result, `submit_call_outcome_to_safeops()`
attaches the caller's own words as an `UNTRUSTED` `voice_call_transcript`
source and submits `refund_payment` to SafeOps -- which returns
`REQUIRES_APPROVAL` at this amount, exactly like the MCP and Strands
refund demos. Approve it as a human operator and poll
`GET /api/integrations/actions/{external_request_id}` to see it reach
`EXECUTED` exactly once.

## Demo 2 -- malicious voice transcript (no live call needed)

```bash
python integrations/calle/demo_malicious.py
```

Simulates the structured outcome a call's transcript-extraction step
could plausibly produce if the person on the phone tried to manipulate
the agent, and runs it through the exact same `submit_call_outcome`-style
SafeOps submission path `agent.py` uses for a real completed call.
**Verified live against the real SafeOps API during this integration's
build:** `BLOCKED` / `ACTION_BLOCKED`, a new `OPEN`/`CRITICAL`
`SecurityIncident`, zero side effects -- same result as the MCP and
Strands malicious demos, this time sourced from a voice transcript
instead of a support ticket.

## Verified so far

- Real `calle-ai` SDK installed and introspected directly (not guessed):
  `CalleClient(api_key=...)`, `.calls.create_and_wait(task=, recipient=,
  result_schema=, idempotency_key=)`, `.calls.get(call_id)`. Idempotency
  is native to the API (`idempotency_key` / `Idempotency-Key` header).
- `demo_malicious.py` run for real against the live SafeOps API: BLOCKED,
  incident created, zero side effects (see above).
- `build_calle_client()` constructs successfully without a real key
  (`httpx.Client` construction doesn't authenticate until first request).

**Run live end to end since**: two real outbound calls placed and
answered, full `REQUIRE_APPROVAL` → human approval → `EXECUTED` (exactly
once) loop verified against the real SafeOps API, plus a real
voicemail/no-answer case and a real already-refunded-payment case, both
handled with zero unsafe side effects. Full detail, transcripts, and IDs:
[`submissions/calle.md`](../submissions/calle.md).

## Known limitations

- Uses blocking `create_and_wait()`, not the webhook flow -- fine for a
  single demo call; a production integration handling many calls
  concurrently should use `webhook_url` instead of polling.
- One call maps to at most one SafeOps action in this demo; a
  multi-request call (e.g. "refund this AND look up my other account")
  would need a richer `result_schema` and multiple submissions, not built
  here to keep this timeboxed.
