# MCP Adapter (Milestone 11)

## The rule, stated once

**External agents never execute tools directly. All actions pass through
the SafeOps ToolGateway.**

`integrations/mcp/server.py` is a protocol translator only. It never
imports from `app.*`, never opens a database connection, and never calls
`ToolGateway` or any other SafeOps internal service. Every MCP tool call
it receives is translated into a plain HTTPS call to the generic
integration API (`POST /api/integrations/actions`) -- the exact same API
and code path `integrations/shared/client.py` and any other external
agent framework use. Deleting this file changes nothing about SafeOps's
security guarantees; it only removes one transport for reaching an
already-fully-authorized API.

## Package and version

Built against the real, installed `mcp==2.2.0` PyPI package (verified
directly against its actual API surface in this milestone, not against
memorized/older SDK conventions -- v2's `Server` class and type surface
differ meaningfully from v1). Pinned in `integrations/mcp/requirements.txt`,
which is deliberately separate from `apps/api/requirements.txt`: this
adapter never runs inside the SafeOps API process.

**Dependency footprint** (transitive, reviewed): starlette, pydantic,
httpx, jsonschema, sse-starlette, cryptography, uvicorn, opentelemetry-api,
pyjwt, anyio. Heavier than a minimal stdio server needs, because the
package also supports HTTP/SSE transports and OAuth this adapter does not
use -- only the stdio transport and low-level `Server` are used here. No
plugin/auto-execution mechanism is loaded; the adapter registers exactly
two handlers (`on_list_tools`, `on_call_tool`) explicitly in code.

## Transport

**stdio**, per the milestone's "prefer simplest" guidance: the adapter is
meant to be spawned as a subprocess by an MCP client (Claude Desktop, an
agent framework, etc.), communicating over stdin/stdout. No HTTP/SSE
server is started by this adapter.

## Configuration

```
SAFEOPS_API_BASE_URL        e.g. http://localhost:8000/api
SAFEOPS_INTEGRATION_TOKEN   bearer token for an INTEGRATION principal
SAFEOPS_AGENT_ID            the SafeOps agent UUID this server acts for
                             (must be mapped via IntegrationAgentMapping)
```

## Tool discovery

`on_list_tools` calls `GET /integrations/tools?safeops_agent_id=...` on
**every** `tools/list` request -- there is no cached/static tool list, so
a permission change made by a SafeOps admin (an `AgentToolPermission` row
flipped to `DENY`) takes effect on the very next call, with no adapter
restart required.

## Tool calls

`on_call_tool` generates a fresh `external_request_id` (`uuid4`) for
every call -- MCP's `call_tool` has no client-supplied idempotency key of
its own, and MCP's transport already guarantees at-most-one delivery per
call, so distinct MCP calls are intentionally never coalesced by the
API's idempotency logic. It then calls `POST /integrations/actions` with
`integration_type: "MCP"` and returns a `CallToolResult` describing the
outcome (`EXECUTED` with the tool's result / `REQUIRES_APPROVAL` with the
`approval_request_id` and polling instructions / `BLOCKED` or `FAILED`
with the stable error code -- never a raw exception traceback).

### Demo-only extension: attaching untrusted context

MCP's `call_tool` arguments have no built-in concept of "attached context
sources" the way the generic API does. This adapter recognizes one
reserved argument key, `_sources`, popped out of the arguments before
they are validated against the tool's own input schema and forwarded
separately as the request's `sources`:

```json
{"to": "x@example.com", "subject": "s", "body": "b",
 "_sources": [{"type": "support_ticket", "content": "..."}]}
```

This is a demo/testing convention documented here, not part of the MCP
protocol. Regardless of what an MCP client claims, every source arriving
this way is still forced to `UNTRUSTED` server-side -- this convention
cannot be used to mark injected content trusted.

## Approval flow through MCP (worked example)

```
$ python integrations/mcp/demo_client.py
Discovered tools: [...]
read_customer -> "Tool 'read_customer' executed. Result: {...}"
refund_payment -> "Tool 'refund_payment' requires human approval before it
  will run (approval_request_id=<uuid>). Poll status with
  external_request_id=<uuid> once the approval has been granted or denied
  by an authorized SafeOps operator; this call does not block waiting for
  that."
```

The MCP call returns immediately -- it never blocks waiting for a human.
Approve it as a human operator, then poll:

```
curl -X POST $SAFEOPS_API_BASE_URL/approvals/<approval_request_id>/approve \
  -H "Authorization: Bearer sfops_demo_approver_signoff" \
  -H "Content-Type: application/json" -d '{"comment": "approved"}'

curl $SAFEOPS_API_BASE_URL/integrations/actions/<external_request_id> \
  -H "Authorization: Bearer $SAFEOPS_INTEGRATION_TOKEN"
# -> {"status": "EXECUTED", "result": {...}, ...}
```

Verified for real, end to end, against a running SafeOps API and the real
`mcp` package (not mocked) during this milestone's implementation.

## Malicious MCP demo

`integrations/mcp/demo_malicious_client.py` drives a prompt-injected
support ticket through `send_external_email` -- a tool support-agent is
directly ALLOWed to call, so neither Permission nor Policy blocks it.
Risk Engine is the layer that stops it:

```
$ python integrations/mcp/demo_malicious_client.py
MALICIOUS SEND_EXTERNAL_EMAIL RESULT: ["Tool 'send_external_email' did not
  execute: BLOCKED - Action blocked by SafeOps."]
is_error: True
```

Verified during implementation: the resulting `ExternalActionRequest` row
is `BLOCKED` / `ACTION_BLOCKED`, a new `SecurityIncident` is created
(`OPEN`, `CRITICAL`), and the corresponding `ToolRequest` shows the tool
was never actually invoked -- zero side effects, exactly as the internal
(non-MCP) version of this same demo has proven since Milestone 7.

## Cross-agent impersonation

An integration token mapped only to `support-agent` gets
`403 AGENT_MAPPING_DENIED` if it names any other `safeops_agent_id`
(e.g. `devops-agent`) on any call, including `tools/list` --
verified directly against the running API during this milestone.

## Local demo checklist

1. `pip install -r integrations/mcp/requirements.txt`
2. Start the API (`uvicorn app.main:app`) against a migrated dev database
   with demo seed data (`python -m app.core.seed`, `SAFEOPS_DEMO_MODE=true`).
3. `SAFEOPS_API_BASE_URL=... SAFEOPS_INTEGRATION_TOKEN=sfops_demo_integration_support SAFEOPS_AGENT_ID=<support-agent uuid> python integrations/mcp/demo_client.py`
4. Approve the pending refund and poll, per the worked example above.
5. Run `integrations/mcp/demo_malicious_client.py` with the same
   environment and confirm `is_error: True`.

## Known limitations

- No HTTP/SSE transport is wired up, only stdio.
- No MCP resources/prompts/sampling support -- tools only.
- The `_sources` argument convention is adapter-specific, not a standard
  MCP mechanism; a different MCP client would need to know about it to
  attach untrusted context the same way.
- See `docs/integrations.md` "Known limitations" for everything that
  applies at the API layer regardless of transport.
