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

export CALLE_API_KEY=...                    # or use `calle auth login` (CLI, browser OAuth)
export CALLE_RECIPIENT_PHONE=+1...          # a real number you can answer
export SAFEOPS_API_BASE_URL=http://localhost:8000/api
export SAFEOPS_INTEGRATION_TOKEN=sfops_demo_integration_support
export SAFEOPS_AGENT_ID=<support-agent UUID from seed output>
# Optional -- override which payment/customer/amount the call is about
# (defaults to PAY-9003 / CUST-1001 / 750.00):
export CALLE_PAYMENT_ID=PAY-9004
export CALLE_CUSTOMER_ID=CUST-1001
export CALLE_REFUND_AMOUNT=750.00
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

## Status — fully verified live, end to end

### 1. Real outbound call placed and completed

Via the official CALL-E CLI (`calle auth login` browser OAuth, then
`calle call plan` / `calle call run` / `calle call status` — the same
`plan_call`/`run_call`/`get_call_run` MCP tools `agent.py`'s Python SDK
path also uses). Two real calls were placed to a real phone number
during testing: the first reached voicemail (a genuine, correctly
non-actionable outcome — see "Duplicate-refund / no-answer handling"
below); the retry reached a live person.

**Live confirmation transcript** (`run_id: nyaPZMaf-JYA7xk_N2Leqg`,
`call_id: 94066dd4add843748b40894f0fc6b6db`, `task_completed: true`,
confidence 0.95):

```
[00:00:00] BOT: Hi.
[00:00:03] USER: Hello?
[00:00:04] BOT: I'm calling for SafeOps customer support about a pending seven hundred fifty dollar refund for a duplicate payment on your account;
[00:00:11] BOT: would you like to proceed with the refund?
[00:00:17] USER: Let me see if 40 on 3. 40 on 3. Yeah. Go ahead.
[00:00:18] BOT: Got it, thanks.
[00:00:19] BOT: So you'd like to proceed with the seven hundred fifty dollar refund for the duplicate payment on your account,
[00:00:23] BOT: correct?
[00:00:26] USER: Yes. Yeah. Right.
[00:00:27] BOT: Thank you, bye.
```

### 2. Approval flow, real and complete

The confirmed outcome was submitted through the unmodified
`SafeOpsClient.submit_action()` path. Result: `REQUIRES_APPROVAL`
(payment $750 crosses the policy threshold), `approval_request_id:
26d9065c-c0b7-4436-bbed-e8ad35c6bdd8`. A human APPROVER operator approved
it; the full audit trail (real, captured live) shows the complete causal
chain in order:

```
EXECUTION_STARTED → EXTERNAL_REQUEST_RECEIVED → EXECUTION_STEP_STARTED →
TOOL_REQUESTED → PERMISSION_CHECKED → POLICY_EVALUATION_STARTED →
POLICY_MATCHED → POLICY_APPROVAL_REQUIRED → RISK_ASSESSMENT_STARTED →
RISK_SIGNAL_DETECTED → RISK_ASSESSED → APPROVAL_REQUESTED →
EXECUTION_WAITING_APPROVAL → APPROVAL_APPROVED → APPROVED_ACTION_EXECUTION_STARTED →
APPROVED_ACTION_EXECUTED
```

### 3. Exactly-once refund proof

- `ToolRequest.status = EXECUTED`, `ExternalActionRequest.status = EXECUTED`
  (the latter confirmed via `GET /api/integrations/actions/{id}`, queried
  **twice** — identical result both times, no re-execution).
- Payment refunded: `PAY-9004` → `REFUNDED`, refund amount `750.00`.
- **Exactly one** `Refund` row exists for `PAY-9004` after both queries.
- Voice transcript stored and confirmed as `type: voice_call_transcript,
  trust: UNTRUSTED` on the executed step — never upgraded to trusted.
- No bearer tokens, credentials, or raw exception text found in any audit
  event's metadata.

### 4. Duplicate-refund / no-answer handling — also verified live

Two separate real-world edge cases, both handled correctly with zero
unsafe side effects:

- **Voicemail (no live confirmation):** the first live call reached
  voicemail. `submit_call_outcome_to_safeops()` correctly returned
  `NO_ACTION` — no `ExternalActionRequest` was created at all, because no
  confirmation was ever obtained. Nothing to duplicate.
- **Already-refunded payment (PAY-9003):** a separate live call outcome
  was submitted against `PAY-9003`, which had already been refunded in an
  earlier demo session. SafeOps still correctly returned
  `REQUIRES_APPROVAL` (policy/risk don't know payment history), but once
  approved, `RefundPaymentTool` refused to refund it a second time
  (`FAILED`, "already refunded") — proving the double-refund guard holds
  even after a human approves.

### 5. Malicious voice transcript → BLOCKED (`demo_malicious.py`)

Run for real against the live SafeOps API: `BLOCKED` / `ACTION_BLOCKED`,
a new `OPEN`/`CRITICAL` `SecurityIncident`, zero side effects (see
`docs/calle.md` for the full captured result).

### Bug found and fixed during this verification

`submit_call_outcome_to_safeops()` originally **hardcoded**
`"payment_id": "PAY-9003"` regardless of what payment a given call was
actually about. Caught by hand when a live call placed about `PAY-9004`
still silently generated a SafeOps submission for `PAY-9003` — the
pending approval was inspected before being approved, the mismatch was
rejected, and the request was correctly resubmitted. Fixed:
`place_refund_confirmation_call()` and `submit_call_outcome_to_safeops()`
now both take `payment_id` (plus `customer_id`/`amount` for the call
task) as required keyword arguments sourced from the actual scenario,
never hardcoded. Regression tests: `integrations/calle/test_agent.py`
(7 tests, all passing).

- Code: `integrations/calle/`, feature originally committed at `beb41de`;
  this bug fix, its regression tests, and this document were committed
  together in the following commit.
