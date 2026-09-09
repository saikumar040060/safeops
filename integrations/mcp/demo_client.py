"""Local MCP demo (milestone spec section 46, flow A/B).

Spawns the real integrations/mcp/server.py as a subprocess over stdio --
exactly how a real MCP client (Claude Desktop, an agent framework, etc.)
would talk to it -- and drives three calls:

  1. tools/list -- discovers the tools support-agent may use, live from
     the real SafeOps API.
  2. read_customer (permission ALLOW, no risk) -- executes immediately.
  3. refund_payment at the $750 approval threshold (permission
     CONDITIONAL) -- comes back REQUIRES_APPROVAL. This script does not,
     and cannot, approve its own action: that would defeat the entire
     point of the approval gate. It prints the approval_request_id and
     external_request_id and exits; approve it as a human operator with:

         curl -X POST $SAFEOPS_API_BASE_URL/approvals/<approval_request_id>/approve \\
           -H "Authorization: Bearer sfops_demo_approver_signoff" \\
           -H "Content-Type: application/json" -d '{"comment": "approved"}'

     then poll for completion with:

         curl $SAFEOPS_API_BASE_URL/integrations/actions/<external_request_id> \\
           -H "Authorization: Bearer $SAFEOPS_INTEGRATION_TOKEN"

     See docs/mcp.md "Approval flow through MCP" for the full worked
     example including expected responses at each step.

Usage:
    SAFEOPS_API_BASE_URL=http://localhost:8000/api \\
    SAFEOPS_INTEGRATION_TOKEN=sfops_demo_integration_support \\
    SAFEOPS_AGENT_ID=<support-agent uuid> \\
    python integrations/mcp/demo_client.py
"""

import asyncio
import os
import sys

import mcp.types as types
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


def _texts(result: types.CallToolResult) -> list[str]:
    return [c.text for c in result.content if isinstance(c, types.TextContent)]


async def main() -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=[os.path.join(os.path.dirname(__file__), "server.py")],
        env=dict(os.environ),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("Discovered tools:", [t.name for t in tools.tools])

            result = await session.call_tool("read_customer", {"customer_id": "CUST-1001"})
            print("read_customer ->", _texts(result))

            result = await session.call_tool(
                "refund_payment",
                {
                    "payment_id": "PAY-9002",
                    "amount": "750.00",
                    "reason": "MCP demo refund",
                    "idempotency_key": "mcp-demo-refund-1",
                },
            )
            print("refund_payment ->", _texts(result))


if __name__ == "__main__":
    asyncio.run(main())
