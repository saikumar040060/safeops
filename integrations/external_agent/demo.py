"""Example: a generic (non-MCP) external agent framework using the
SafeOps SDK client directly against the generic REST API. This is the
"External Agent Client" path from the milestone architecture diagram --
no MCP protocol involved at all, just HTTP.

Usage:
    SAFEOPS_API_BASE_URL=http://localhost:8000/api \\
    SAFEOPS_INTEGRATION_TOKEN=sfops_demo_integration_support \\
    SAFEOPS_AGENT_ID=<support-agent uuid> \\
    python integrations/external_agent/demo.py
"""

import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shared"))

from client import SafeOpsAPIError, SafeOpsClient  # noqa: E402


def main() -> None:
    base_url = os.environ.get("SAFEOPS_API_BASE_URL", "http://localhost:8000/api")
    token = os.environ["SAFEOPS_INTEGRATION_TOKEN"]
    agent_id = os.environ["SAFEOPS_AGENT_ID"]

    client = SafeOpsClient(base_url, token)

    tools = client.list_tools(safeops_agent_id=agent_id)
    print(f"Discovered {len(tools)} tools this integration may call:")
    for tool in tools:
        print(f"  - {tool['name']}: {tool['description']}")

    action = client.submit_action_with_retry(
        external_request_id=f"external-agent-demo-{uuid.uuid4()}",
        safeops_agent_id=agent_id,
        tool_name="read_customer",
        arguments={"customer_id": "CUST-1001"},
        objective="Generic external-agent SDK demo: look up a customer",
    )
    print("submit_action result:", action)

    try:
        client.get_action("does-not-exist")
    except SafeOpsAPIError as exc:
        print(f"Expected error looking up unknown action: {exc.code} {exc.message}")


if __name__ == "__main__":
    main()
