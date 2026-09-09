# AWS Strands Adapter

## The rule, stated once

**External agents never execute tools directly. All actions pass through
the SafeOps ToolGateway.**

`integrations/strands/agent.py` builds a real `strands.Agent` (the
official [AWS Strands Agents SDK](https://github.com/strands-agents/harness-sdk),
`strands-agents` on PyPI) whose only tools
(`integrations/strands/tools.py`) are thin wrappers around the same
generic SafeOps integration API the MCP adapter and generic SDK use
(`POST /api/integrations/actions` via `integrations/shared/client.py`).
Neither file imports from `app.*`, touches a database, or calls
ToolGateway/a tool implementation directly. If the agent's own LLM
reasoning decided to call `refund_payment` unprompted, that call still has
to pass Permission -> Policy -> Risk -> Approval before anything happens,
because that is the only thing `client.submit_action()` does.

## Configuration

```
SAFEOPS_API_BASE_URL        e.g. http://localhost:8000/api
SAFEOPS_INTEGRATION_TOKEN   bearer token for an INTEGRATION principal
SAFEOPS_AGENT_ID            the SafeOps agent UUID this agent acts for
                             (must be mapped via IntegrationAgentMapping)

# Model provider -- pick one:
ANTHROPIC_API_KEY           uses strands.models.anthropic.AnthropicModel
# or, if not set, falls back to strands.models.BedrockModel, which needs
# a configured AWS credential chain (env vars / ~/.aws/credentials / a
# role) with model access enabled for the target Bedrock model/region.

STRANDS_MODEL_ID             optional override for either provider above
```

## Tools

`read_customer`, `get_payments`, `refund_payment`, `get_support_ticket`,
`send_external_email` -- each a `@tool`-decorated function whose type
hints and docstring Strands turns into the tool's JSON schema (verified
by hand: the generated schemas match SafeOps' own tool argument shapes
exactly). Reading a support ticket taints the rest of that tool set's
calls: the ticket body is attached as an `UNTRUSTED` source on every
subsequent SafeOps submission from the same `build_tools(...)` instance,
so a later `send_external_email` triggered by a prompt-injected ticket
carries the context Risk Engine needs to catch it -- the same mechanism
as the MCP adapter's `_sources` convention, just modeled at the
tool-wrapper layer since neither MCP's `call_tool` nor a Strands `@tool`
function has a native "attached untrusted context" concept of its own.

## Demo

```bash
pip install -r integrations/strands/requirements.txt

export SAFEOPS_API_BASE_URL=http://localhost:8000/api
export SAFEOPS_INTEGRATION_TOKEN=sfops_demo_integration_support   # seeded demo token
export SAFEOPS_AGENT_ID=<support-agent UUID>
export ANTHROPIC_API_KEY=...        # or configure AWS credentials for Bedrock

python integrations/strands/agent.py \
  "Investigate the duplicate payment for customer CUST-1001 and refund the duplicate."

python integrations/strands/demo_malicious.py   # TCK-4837 prompt-injection demo
```

Expected flow for the first command: the agent calls `read_customer` and
`get_payments`, finds the duplicate $750 charge (`PAY-9003`), and proposes
`refund_payment`. That amount crosses this policy's approval threshold, so
SafeOps returns `REQUIRES_APPROVAL` instead of executing it -- approve it
as a human operator (dashboard or `POST /api/approvals/{id}/approve`) and
poll `GET /api/integrations/actions/{external_request_id}` to see it
reach `EXECUTED` exactly once, same as the MCP worked example in
[`docs/mcp.md`](mcp.md).

For `demo_malicious.py`: this drives a real LLM reasoning loop, not a
scripted tool call (unlike the deterministic internal version of this
same demo, `apps/api/tests/test_risk_gateway_integration.py`), so whether
the agent actually attempts the injected instruction depends on model
behavior. If it does, expect `BLOCKED` with zero side effects; if the
model refuses to act on the ticket's instructions on its own, that is a
second, independent layer of safety on top of SafeOps, not a failure of
either.

## Verified so far

Structurally verified without a live model call: `build_agent()`
constructs successfully (Bedrock's client is lazily authenticated, so
this succeeds even with no AWS credentials configured), all five tools
register on the `Agent` with correct names, and their generated
`tool_spec` JSON schemas match SafeOps' own tool argument shapes exactly.
**Not yet run against a live model** -- that needs either an
`ANTHROPIC_API_KEY` or working AWS Bedrock credentials with model access,
neither of which is available in this environment; see the milestone
report for the exact remaining step.

## Known limitations

- No push/webhook for approval resolution -- same polling-only model as
  every other integration; see `docs/integrations.md`.
- The "taint the rest of this tool set's calls" mechanism is
  process/instance-local (a fresh `build_tools()` call starts untainted);
  it does not persist across separate agent runs.
