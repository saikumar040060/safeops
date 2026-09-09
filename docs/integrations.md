# External Agent Integration Layer (Milestone 11)

## The rule, stated once

**External agents never execute tools directly. All actions pass through
the SafeOps ToolGateway.**

Every route in this integration layer -- the generic REST API and the MCP
adapter alike -- is a thin translator in front of the exact same
Permission -> Policy -> Risk -> Approval pipeline every internal,
planner-driven tool call already goes through. There is no second,
weaker authorization path for external callers. `test_integrations_security.py::test_no_route_bypasses_tool_gateway`
enforces this structurally by grepping the codebase for any `.execute(`
call outside the files that are allowed to reach the tool registry.

## Architecture

```
External Agent / MCP Client
        |
        v
integrations/mcp/server.py  (protocol translator, stdio; no DB access)
integrations/shared/client.py (generic HTTP SDK; used by both MCP adapter
                                and any other external agent framework)
        |
        v  HTTPS, bearer token
apps/api  POST /api/integrations/actions
          GET  /api/integrations/actions/{external_request_id}
          GET  /api/integrations/tools
        |
        v
ExternalActionService
        |
        v
AgentRuntime.submit_external_action() / reconcile_external_step()
   (thin wrappers around the SAME internal _run_tool_call_step() /
    _resolve_pending_step() helpers step()/resume() already use)
        |
        v
ToolGateway.execute()  <-- unchanged; this milestone adds no new
                            authorization logic here
```

`integrations/mcp/` and `integrations/shared/` never import from `app.*`,
never open a database connection, and never call `ToolGateway` or any
other internal service directly. If either directory were deleted
entirely, no SafeOps security guarantee would change -- only a transport
for reaching the API would disappear.

## Two authorization dimensions

SafeOps has always had role-based authorization for human operators
(`require_permission`, `OperatorRole` -> `read`/`execute`/`approve`).
Milestone 11 adds a second, independent dimension for machine
(`INTEGRATION`) principals: `require_scope`, checked against a plain list
of scopes on the `Operator` row (`integration_scopes`). These two
dimensions never cross:

- Every `INTEGRATION` operator row has `role = VIEWER` as defense in
  depth -- even if `require_scope` had a bug, `require_permission` would
  still refuse it `execute`/`approve`.
- `approvals:approve` is never an integration scope. This codebase does
  not issue it to any integration, ever, and there is no configuration
  path that grants it. An external agent cannot approve its own escalated
  action, no matter how over-provisioned its token is. See
  `test_integrations_security.py` for the explicit self-approval-denial
  test.

Available integration scopes: `actions:submit`, `actions:read`,
`executions:read`, `executions:create`, `incidents:read`.

## Agent identity: caller-claimed vs. authorized

A request may include a caller-claimed `external_agent_id` (opaque,
informational only -- logged, never trusted for authorization). The
field that actually matters is `safeops_agent_id`: a real SafeOps `Agent`
UUID that the integration must be explicitly mapped to via
`IntegrationAgentMapping` (`operator_id`, `agent_id`, unique together).
There is no default mapping and no wildcard: an integration token with no
mapping row for a given agent gets `403 AGENT_MAPPING_DENIED` on every
call naming that agent, including on `GET /integrations/tools`. This is
what stops the cross-agent impersonation attack (an integration
authenticated as one agent's assistant claiming to act as a
higher-privileged agent) -- verified in
`test_integrations_security.py`.

## Idempotency

Every submitted action carries a client-generated `external_request_id`.
The database enforces `UNIQUE(operator_id, external_request_id)` --
concurrent duplicate submissions race the constraint itself (not a
check-then-insert, which would be a TOCTOU gap under real concurrency),
and the loser is redirected to the winner's row. If a retried request's
payload doesn't match the original (compared by a canonical SHA-256 hash,
`app/core/canonical.py`), it is rejected with `409 IDEMPOTENCY_CONFLICT`
rather than silently executing a different action under the same key.

## Crash-recovery semantics (stated precisely, not overclaimed)

This is **not** exactly-once execution in the distributed-systems sense.
What is actually guaranteed:

- The `ExternalActionRequest` row, once inserted, is the durable
  checkpoint for a given `(operator_id, external_request_id)`.
- Before ever re-invoking the runtime for a retried/duplicate request,
  the service checks whether a matching `ExecutionStep` (same tool,
  status != PENDING) already recorded that tool call's outcome, and
  derives the response from it instead of re-calling the gateway. This is
  the same "check history before resubmitting" principle
  `DeterministicPlanner._attempted()` already relies on internally,
  applied at the integration-service layer.
- A request that loses the stepping-lease race against a concurrent
  identical submission may legitimately receive a transient
  `503 ACTION_PROCESSING_CONFLICT`. This is expected, retry-safe
  behavior, not a bug -- retry with the **same** `external_request_id`.

## Approval flow, correlated by reading, not by pushing

When a submitted action needs human sign-off, the response is
`REQUIRES_APPROVAL` with an `approval_request_id`, returned immediately
(never blocked on). `ApprovalEngine` has no knowledge of the integration
layer and no code that calls back into it -- zero coupling in that
direction. Instead, `GET /integrations/actions/{external_request_id}`
(and the idempotent-replay path on a repeated `POST`) checks the linked
`ApprovalRequest.status`; only once it has moved past `PENDING` does the
service call `AgentRuntime.reconcile_external_step()`, which resolves the
waiting step and nothing else -- deliberately never re-invokes the
planner, since there is no planner-owned "next step" for an
externally-driven action.

Worked example:

```
POST /api/integrations/actions  {tool_name: "refund_payment", amount: 750.00, ...}
  -> 200 {status: "REQUIRES_APPROVAL", approval_request_id: "...", external_request_id: "..."}

# a human APPROVER operator approves via the existing approvals API/UI
POST /api/approvals/{approval_request_id}/approve

GET /api/integrations/actions/{external_request_id}
  -> 200 {status: "EXECUTED", result: {...}}
```

## Context and trust

Every source an external caller attaches to a request (`sources: [{type,
content}]`) is forced to `UNTRUSTED` by `ExternalActionService`,
unconditionally, in this milestone -- there is no per-integration
trust-upgrade configuration. A caller cannot mark its own injected
content trusted by setting a field; `SourceInput` has no `trust` field at
all. Risk Engine (Milestone 7) evaluates these sources exactly as it
would any other untrusted context, whether the call originated
internally or externally.

## Generic SDK client

`integrations/shared/client.py` (`SafeOpsClient`) is a plain
`requests`-based HTTP client any agent framework can use directly --
`list_tools()`, `submit_action()`, `get_action()`,
`submit_action_with_retry()`, `poll_until_complete()`. It is the same
client the bundled MCP adapter uses internally; there is no special,
undocumented internal API.

**Retry policy** (`submit_action_with_retry`): the same
`external_request_id` is used on every attempt -- never regenerated on
retry, since that is the entire idempotency contract. 4xx responses are
never retried (a stable, permanent verdict). 5xx and 429 responses are
retried with exponential backoff, since the server guarantees idempotent
processing keyed on `(operator_id, external_request_id)`.

See `integrations/external_agent/demo.py` for a runnable example.

## Rate limits (per integration operator)

| Endpoint                         | Limit            |
|-----------------------------------|-----------------|
| `POST /integrations/actions`      | 30 / 60s         |
| `GET /integrations/actions/{id}`  | 120 / 60s        |
| `GET /integrations/tools`         | 60 / 60s         |

Same in-process, per-worker limiter as the rest of the API (see
`app/core/rate_limit.py`); documented multi-worker limitation applies
here too.

## Observability

`GET /api/metrics` (existing endpoint, requires `read` permission) adds:
`external_requests_total`, `external_requests_blocked_total`,
`external_requests_waiting_approval`, `mcp_tool_calls_total`,
`integration_auth_failures_total`, `idempotency_conflicts_total`. The
last two are in-process counters (never persisted as a row, since an
auth failure or a rejected conflicting payload must not mutate state) --
same non-aggregated-across-workers limitation as everything else in
`app/core/metrics.py`.

## Error model

Every error response is `{code, message}` with a stable, documented
`code` (`AGENT_MAPPING_DENIED`, `UNKNOWN_AGENT`, `UNKNOWN_EXECUTION`,
`IDEMPOTENCY_CONFLICT`, `ACTION_PROCESSING_CONFLICT`, `ACTION_BLOCKED`,
`UNKNOWN_ACTION`, `INSUFFICIENT_SCOPE`, ...). Raw exception text is never
returned to an external caller.

## Known limitations (explicit, not hidden)

- Idempotency conflicts and integration auth failures are counted
  in-process only; with more than one API worker, `/api/metrics` reports
  per-worker counts, not a combined total.
- There is no per-integration trust-upgrade configuration for sources --
  every externally supplied source is UNTRUSTED, always.
- Result delivery is polling-only; there is no webhook/push mechanism.
- Agent-to-integration mapping is a flat, admin-configured table; there is
  no self-service mapping UI in this milestone.
- Docs and demos here cover the generic API and the MCP stdio adapter
  only. AWS Strands integration is prepared at the interface level only
  (no AWS dependencies); CALL-E/Twilio, billing, and multi-tenancy are out
  of scope for this milestone.

See `docs/mcp.md` for the MCP-specific adapter, and
`integrations/mcp/demo_client.py` / `demo_malicious_client.py` /
`integrations/external_agent/demo.py` for runnable, verified demos.
