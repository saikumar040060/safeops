# CALL-E submission — SafeOps + CALL-E

Hackathon: **CALL-E: Your Code Is Calling** ([call-e.devpost.com](https://call-e.devpost.com)) — deadline **September 14, 2026, 11:45 PM SGT**.

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

## Demo script — under 3 minutes (judges are not required to watch past this)

Since a live phone call itself can take 30–60+ seconds and isn't
scriptable to a fixed length, this script leans on **pre-recorded / cut
footage** from the verified live run below rather than dialing on
camera — that keeps the total under 3 minutes reliably.

| Time | Content |
|---|---|
| 0:00–0:20 | **Pitch, fast**: "CALL-E gives code a phone line. A phone call is unstructured, human, and can be adversarial — exactly the kind of input a security system should never trust blindly. This is CALL-E wired to SafeOps, an independent authorization layer, so a call's outcome still has to be approved before anything happens." |
| 0:20–0:35 | **Code shot**: `integrations/calle/agent.py` — `submit_call_outcome_to_safeops()` is the only place a call's result becomes a SafeOps action, via the same `SafeOpsClient.submit_action()` every other integration uses. |
| 0:35–1:20 | **Cut to the real call recording/transcript**: CALL-E asks the customer to confirm a $750 duplicate-payment refund; customer confirms twice ("Yeah. Go ahead." → re-confirmed "Yes. Yeah. Right."). |
| 1:20–1:45 | **Show SafeOps response**: terminal output — `REQUIRES_APPROVAL`. Cut to the dashboard Approval Center showing the pending request with the call transcript attached as its (untrusted) source. |
| 1:45–2:10 | **Approve it**: show the execution timeline reach `EXECUTED`, exactly once. |
| 2:10–2:40 | **Malicious variant** (deterministic, fast to show): `python integrations/calle/demo_malicious.py` — terminal shows `BLOCKED`; cut to the Security Center incident it creates. |
| 2:40–3:00 | **Close**: same SafeOps authorization boundary as the MCP and Strands submissions — one security model behind three different ways an agent can act. |

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
  the payment_id bug fix, its regression tests, and the live-run write-up
  above were committed together at `ae429cb`.

## PR checklist (required for submission — not yet done)

The hackathon requires opening a pull request against the **public**
repo `https://github.com/CALLE-AI/awesome-phone-call-agents`, following
that repo's own README for the correct contribution area, and providing
the PR URL on the Devpost submission form. None of this has been done
yet. Steps:

- [ ] Read `CALLE-AI/awesome-phone-call-agents`' README for the exact
      contribution format/directory it expects (this repo is external —
      not inspected yet).
- [ ] Fork it, add an entry for this project (name, one-line description,
      link back to `saikumar/safeops` and/or a demo video).
- [ ] Confirm whether `integrations/calle/` needs to be public for the
      linked entry to be useful to reviewers — see "Repository visibility"
      in `submissions/README.md`.
- [ ] Open the PR, get its URL.
- [ ] Paste that PR URL into the Devpost submission form (`call-e.devpost.com`).
- [ ] Provide the email address associated with your CALL-E account on
      the submission form (separate requirement, not code-related).
