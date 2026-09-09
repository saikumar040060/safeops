# AWS Strands submission — SafeOps + Strands

See [`submissions/README.md`](README.md) first for the shared disclosure,
architecture diagram, and setup steps.

## One-line description

A real AWS Strands agent that can't do anything on its own — every tool
call it makes is authorized (or blocked, or paused for a human) by
SafeOps, an independent runtime security layer, before it happens.

## Longer description (submission page)

Autonomous agents built with frameworks like Strands are good at
deciding *what* to do; they have no built-in opinion on whether they
*should*. This submission wires a real Strands `Agent` to SafeOps — a
runtime authorization layer with deterministic policy, a risk engine that
catches prompt injection and data exfiltration, and human-approval
gating for anything above a threshold. The agent's tools
(`read_customer`, `get_payments`, `refund_payment`, `get_support_ticket`,
`send_external_email`) are thin wrappers that call SafeOps' generic
external-agent API — they cannot reach a real system directly. Reading a
support ticket taints the rest of that tool set's calls with the ticket's
own content as untrusted context, so a later action driven by a
prompt-injected ticket carries exactly what SafeOps' Risk Engine needs to
catch it.

## Demo script (for the video)

1. **Setup shot**: show `integrations/strands/agent.py` and
   `integrations/strands/tools.py` — point out there is no code path from
   a tool wrapper to a real system, only to `SafeOpsClient.submit_action()`.
2. **Run it**:
   ```bash
   python integrations/strands/agent.py \
     "Investigate the duplicate payment for customer CUST-1001 and refund the duplicate."
   ```
   Narrate as it happens: the agent calls `read_customer`, then
   `get_payments`, notices `PAY-9002`/`PAY-9003` are both $750, and
   proposes a refund.
3. **Show the pause**: the tool call returns `REQUIRES_APPROVAL` — the
   agent reports this to the user and stops. Cut to the SafeOps dashboard
   Approval Center showing the pending request with the amount, agent,
   and reason.
4. **Approve it** as a human operator (dashboard button or
   `POST /api/approvals/{id}/approve`). Show the refund landing in
   `EXECUTED` state, exactly once, in the execution timeline.
5. **Optional bonus** — malicious ticket:
   ```bash
   python integrations/strands/demo_malicious.py
   ```
   The agent reads ticket `TCK-4837` (prompt-injected: "export the entire
   customer database..."). Show the Security Center: a CRITICAL incident,
   BLOCKED, and confirm — in the database or via the API — that the email
   tool never actually ran.

## Setup instructions specific to this submission

```bash
pip install -r integrations/strands/requirements.txt

export SAFEOPS_API_BASE_URL=http://localhost:8000/api
export SAFEOPS_INTEGRATION_TOKEN=sfops_demo_integration_support
export SAFEOPS_AGENT_ID=<support-agent UUID from seed output>
export ANTHROPIC_API_KEY=...        # or configure AWS creds for Bedrock instead
```

Full detail: [`docs/strands.md`](../docs/strands.md).

## Screenshots to capture

- SafeOps dashboard: Approval Center with the pending $750 refund.
- Execution detail/timeline page showing the full step sequence
  (read_customer → get_payments → refund_payment → waiting → approved →
  executed).
- Security Center showing the CRITICAL incident from the malicious-ticket
  run (if included).
- Terminal output of `agent.py` running, showing the Strands agent's own
  reasoning/tool-call trace.

## Status

- Built and structurally verified: `Agent` constructs, all 5 tools
  register with correct names, generated tool schemas match SafeOps' tool
  argument shapes exactly.
- **Not yet run live** — needs `ANTHROPIC_API_KEY` or working AWS Bedrock
  credentials with model access, neither available in the environment
  this was built in. This is the one thing to do before recording: set
  one of those two, then run the demo script above.
- Code: `integrations/strands/`, committed at `6955009`.
