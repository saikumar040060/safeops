import uuid

from app.models import Agent
from app.services.agent_runtime import AgentRuntime

runtime = AgentRuntime()


def test_list_agents_returns_seeded_agents(viewer_client):
    response = viewer_client.get("/api/agents")
    assert response.status_code == 200
    names = {a["name"] for a in response.json()}
    assert names == {"support-agent", "devops-agent"}


def test_agent_detail_includes_permissions_and_executions(viewer_client, seeded_db):
    agent = seeded_db.query(Agent).filter_by(name="support-agent").one()
    runtime.start_execution(agent_id=agent.id, objective="test objective", db=seeded_db)

    response = viewer_client.get(f"/api/agents/{agent.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "support-agent"

    permissions = {p["tool_name"]: p["permission"] for p in body["permissions"]}
    assert permissions["read_customer"] == "ALLOW"
    assert permissions["read_logs"] == "DENY"
    assert permissions["refund_payment"] == "CONDITIONAL"

    assert len(body["recent_executions"]) == 1
    assert body["recent_executions"][0]["objective"] == "test objective"


def test_agent_detail_unknown_id_returns_404(viewer_client):
    response = viewer_client.get(f"/api/agents/{uuid.uuid4()}")
    assert response.status_code == 404
