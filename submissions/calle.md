# CALL-E submission — SafeOps + CALL-E

See [`submissions/README.md`](README.md) first for the shared disclosure,
architecture diagram, and setup steps.

## One-line description

CALL-E makes the phone call and finds out what the customer wants;
SafeOps decides whether that's actually allowed to happen.

## Longer description (submission page)

CALL-E gives code a phone line — it can hold a real conversation and hand
back a structured answer. That's powerful, and also exactly the kind of
input a security-conscious system should never trust blindly: a phone
call is unstructured, human, and can be adversarial. This submission
treats a completed CALL-E call the same way SafeOps already treats a
support ticket or an MCP tool call: the caller's own words are attached
as untrusted context, and whatever action the call's outcome implies has
to pass through SafeOps' Permission → Policy → Risk → Approval pipeline
before anything happens. CALL-E never executes a SafeOps action directly
— it only answers a question.

## Demo script (for the video)

1. **Setup shot**: show `integrations/calle/agent.py` — highlight that
   `submit_call_outcome_to_safeops()` is the only place a call's result
   becomes a SafeOps action, and it goes through the same
   `SafeOpsClient.submit_action()` every other integration uses.
2. **Run the real call**:
   ```bash
   python integrations/calle/agent.py
   ```
   CALL-E calls the demo phone number and asks whether to proceed with a
   $750 refund for a duplicate payment. Answer "yes" on the call.
3. **Show the result**: the script prints CALL-E's structured result,
   then SafeOps' response — `REQUIRES_APPROVAL`, because $750 crosses
   this policy's threshold, exactly like the internal and MCP refund
   demos. Cut to the dashboard Approval Center.
4. **Approve it**, show the refund reach `EXECUTED` exactly once in the
   execution timeline, with the call transcript visible as the attached
   (untrusted) source on that step.
5. **Malicious variant** (no live call needed, deterministic):
   ```bash
   python integrations/calle/demo_malicious.py
   ```
   Simulates a manipulated call transcript trying to get the agent to
   export customer data. Show the terminal output (`BLOCKED`) and the
   Security Center incident it creates.

## Setup instructions specific to this submission

```bash
pip install -r integrations/calle/requirements.txt

export CALLE_API_KEY=...
export CALLE_RECIPIENT_PHONE=+1...          # a real number you can answer
export SAFEOPS_API_BASE_URL=http://localhost:8000/api
export SAFEOPS_INTEGRATION_TOKEN=sfops_demo_integration_support
export SAFEOPS_AGENT_ID=<support-agent UUID from seed output>
```

Full detail, including why this maps CALL-E's outbound-call API onto a
"customer calls in" scenario: [`docs/calle.md`](../docs/calle.md).

## Screenshots to capture

- Terminal output of the real call: CALL-E's structured result printed,
  then SafeOps' `REQUIRES_APPROVAL` response.
- SafeOps dashboard: the pending approval, with the call transcript
  visible as the step's attached source.
- Execution timeline after approval: `EXECUTED`, exactly once.
- Security Center incident from the malicious-transcript demo.

## Status

- Built and verified for real against the live SafeOps API: the
  malicious-transcript path (`demo_malicious.py`) was actually run —
  result: `BLOCKED`, `ACTION_BLOCKED`, a new `OPEN`/`CRITICAL`
  `SecurityIncident`, zero side effects.
- `CalleClient` construction verified without a real key (no network call
  happens until the first request).
- **Not yet run live** — the real phone call in `agent.py` needs a real
  `CALLE_API_KEY` and a phone number to call, neither available in the
  environment this was built in. This is the one thing to do before
  recording: set both, then run `python integrations/calle/agent.py` and
  actually answer the call.
- Code: `integrations/calle/`, committed at `beb41de`.
