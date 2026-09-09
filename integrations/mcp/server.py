"""MCP stdio adapter for SafeOps.

Security boundary, stated once here because it is the single most
important fact about this file: this adapter is a PROTOCOL TRANSLATOR
ONLY. It never imports from `app.*`, never opens a database connection,
and never calls ToolGateway or any other SafeOps internal service. Every
tool call it receives from an MCP client is translated into a plain HTTPS
call to the generic external-agent API (`/api/integrations/*`) using
`integrations.shared.client.SafeOpsClient` -- the exact same API and code
path any other external agent framework would use. If this file were
deleted entirely, no SafeOps security guarantee would change; only one
transport for reaching the (already fully authorized/validated) API would
disappear.

Concretely, this means:
  - Tool discovery (`list_tools`) always asks the real API
    (`GET /integrations/tools`) fresh -- there is no cached/static tool
    list here, so a permission change made by a SafeOps admin takes
    effect on an MCP client's very next `tools/list` call.
  - Tool calls (`call_tool`) always go through `POST /integrations/actions`
    -- Permission -> Policy -> Risk -> Approval all apply exactly as they
    would to any other external caller. A malicious or buggy MCP client
    cannot reach a tool's actual implementation by any path through this
    file.
  - Every MCP tool call gets a freshly generated `external_request_id`
    (MCP's `call_tool` protocol has no client-supplied idempotency key of
    its own), so distinct MCP calls are never coalesced by the API's
    idempotency logic -- correct, since MCP already guarantees at-most-one
    delivery per call over its own transport.
  - An approval-pending result is returned to the MCP client immediately
    (not blocked on), with instructions for how to poll -- see docs/mcp.md
    "Approval flow through MCP" for the full worked example.

Configuration (environment variables):
  SAFEOPS_API_BASE_URL   e.g. http://localhost:8000/api
  SAFEOPS_INTEGRATION_TOKEN
  SAFEOPS_AGENT_ID       the SafeOps agent UUID this server acts on behalf
                         of (must be mapped to the integration token via
                         IntegrationAgentMapping, or every call fails with
                         AGENT_MAPPING_DENIED)
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Any

import mcp.types as types
from mcp.server.lowlevel.server import Server, ServerRequestContext
from mcp.server.stdio import stdio_server
from mcp.shared.exceptions import MCPError

logger = logging.getLogger("safeops.mcp")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))

from client import SafeOpsAPIError, SafeOpsClient, Source  # noqa: E402


def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"missing required environment variable: {name}")
    return value


def _parse_sources(raw_sources: Any) -> list[Source] | None:
    """Strict, defensive parsing of the `_sources` convention (see
    on_call_tool below): malformed shapes must never reach an unguarded
    dict/attribute access, since an uncaught exception here would
    otherwise propagate out of the handler and the underlying `mcp`
    package's own dispatcher falls back to putting the raw Python
    exception message on the wire (`ErrorData(code=0, message=str(e))`,
    see mcp/shared/jsonrpc_dispatcher.py) -- confirmed by hand against a
    malformed `_sources: ["not-a-dict"]` call during this milestone's
    security review. Raising ValueError here is still caught by the
    handler's own catch-all below, which never echoes exception text."""
    if not raw_sources:
        return None
    if not isinstance(raw_sources, list):
        raise ValueError("_sources must be a list")
    parsed: list[Source] = []
    for item in raw_sources:
        if not isinstance(item, dict) or not isinstance(item.get("type"), str):
            raise ValueError("_sources entries must be objects with string 'type'/'content'")
        content = item.get("content")
        if not isinstance(content, str):
            raise ValueError("_sources entries must be objects with string 'type'/'content'")
        parsed.append(Source(type=item["type"], content=content))
    return parsed


def build_server(client: SafeOpsClient, safeops_agent_id: str) -> Server:
    async def on_list_tools(
        context: ServerRequestContext, params: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        try:
            descriptors = await asyncio.to_thread(
                client.list_tools, safeops_agent_id=safeops_agent_id
            )
        except SafeOpsAPIError as exc:
            # A stable, curated error (never raw exception text) reaches
            # the wire via MCPError's own ErrorData -- see on_call_tool's
            # comment for why this matters.
            raise MCPError(
                code=types.INTERNAL_ERROR, message=f"SafeOps tool discovery failed: {exc.code}"
            ) from exc
        except Exception as exc:
            logger.exception("on_list_tools failed")
            raise MCPError(
                code=types.INTERNAL_ERROR, message="SafeOps tool discovery failed unexpectedly"
            ) from exc
        tools = [
            types.Tool(
                name=d["name"],
                description=d["description"],
                input_schema=d["input_schema"],
            )
            for d in descriptors
        ]
        return types.ListToolsResult(tools=tools)

    async def on_call_tool(
        context: ServerRequestContext, params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        external_request_id = str(uuid.uuid4())
        arguments = dict(params.arguments or {})
        # Demo/extension convention, NOT part of the MCP protocol itself:
        # a reserved "_sources" argument key lets an MCP client attach
        # untrusted context (e.g. the body of a support ticket a tool call
        # is acting on) alongside a tool call, forwarded to the API as
        # `sources` rather than as a tool argument. It is always stripped
        # before the remaining arguments are validated against the tool's
        # own input schema, and ExternalActionService forces every one of
        # these to UNTRUSTED regardless of what the client claims (see
        # app/services/external_action_service.py::_normalize_sources) --
        # this convention cannot be used to mark injected content trusted.
        raw_sources = arguments.pop("_sources", None)
        try:
            sources = _parse_sources(raw_sources)
            action = await asyncio.to_thread(
                client.submit_action,
                external_request_id=external_request_id,
                safeops_agent_id=safeops_agent_id,
                tool_name=params.name,
                arguments=arguments,
                objective=f"MCP tool call: {params.name}",
                sources=sources,
                integration_type="MCP",
            )
        except SafeOpsAPIError as exc:
            # A stable, never-raw-exception-text error code/message from
            # the API (see spec section 40) -- safe to surface verbatim to
            # the MCP client, unlike an internal traceback.
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=f"{exc.code}: {exc.message}")],
                is_error=True,
            )
        except Exception:
            # Last-resort safety net: without this, an unexpected exception
            # (malformed `_sources`, a network error, ...) propagates out of
            # this handler and the underlying `mcp` package's own dispatcher
            # falls back to putting the raw Python exception message on the
            # wire verbatim (confirmed by hand during this milestone's
            # security review -- see _parse_sources' docstring). Never
            # str(exc) here, for the same reason the API layer never
            # returns raw exception text.
            logger.exception("on_call_tool failed for tool %r", params.name)
            return types.CallToolResult(
                content=[
                    types.TextContent(
                        type="text",
                        text="INTERNAL_ERROR: the request could not be processed.",
                    )
                ],
                is_error=True,
            )

        status = action["status"]
        if status == "EXECUTED":
            text = f"Tool '{params.name}' executed. Result: {action.get('result')}"
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=text)], is_error=False
            )
        if status == "REQUIRES_APPROVAL":
            text = (
                f"Tool '{params.name}' requires human approval before it will run "
                f"(approval_request_id={action.get('approval_request_id')}). "
                f"Poll status with external_request_id={external_request_id!r} "
                "once the approval has been granted or denied by an authorized "
                "SafeOps operator; this call does not block waiting for that."
            )
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=text)], is_error=False
            )
        # BLOCKED / FAILED / PROCESSING
        text = f"Tool '{params.name}' did not execute: {status} - {action.get('message')}"
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=text)], is_error=True
        )

    return Server("safeops", on_list_tools=on_list_tools, on_call_tool=on_call_tool)


async def main() -> None:
    base_url = os.environ.get("SAFEOPS_API_BASE_URL", "http://localhost:8000/api")
    token = _env("SAFEOPS_INTEGRATION_TOKEN")
    agent_id = _env("SAFEOPS_AGENT_ID")

    client = SafeOpsClient(base_url, token)
    server = build_server(client, agent_id)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
