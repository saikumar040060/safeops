import uuid

from app.models import Agent
from app.services.agent_runtime import AgentRuntime

runtime = AgentRuntime()


def _agent(db, name) -> Agent:
    return db.query(Agent).filter_by(name=name).one()


def test_audit_filters_by_execution(viewer_client, seeded_db):
    agent = _agent(seeded_db, "support-agent")
    start_a = runtime.start_execution(agent_id=agent.id, objective="a", db=seeded_db)
    start_b = runtime.start_execution(agent_id=agent.id, objective="b", db=seeded_db)

    response = viewer_client.get("/api/audit", params={"execution_id": start_a.execution_id})
    assert response.status_code == 200
    events = response.json()
    assert len(events) == 1
    assert events[0]["execution_id"] == start_a.execution_id
    assert all(e["execution_id"] != start_b.execution_id for e in events)


def test_audit_filters_by_agent(viewer_client, seeded_db):
    support = _agent(seeded_db, "support-agent")
    devops = _agent(seeded_db, "devops-agent")
    runtime.start_execution(agent_id=support.id, objective="a", db=seeded_db)
    runtime.start_execution(agent_id=devops.id, objective="b", db=seeded_db)

    response = viewer_client.get("/api/audit", params={"agent_id": str(support.id)})
    events = response.json()
    assert len(events) == 1
    assert events[0]["actor"] == "support-agent"


def test_audit_filters_by_event_type(viewer_client, seeded_db):
    agent = _agent(seeded_db, "support-agent")
    runtime.start_execution(agent_id=agent.id, objective="a", db=seeded_db)
    runtime.start_execution(agent_id=agent.id, objective="b", db=seeded_db)

    response = viewer_client.get("/api/audit", params={"event_type": "EXECUTION_STARTED"})
    events = response.json()
    assert len(events) == 2
    assert all(e["event_type"] == "EXECUTION_STARTED" for e in events)


def test_audit_pagination(viewer_client, seeded_db):
    agent = _agent(seeded_db, "support-agent")
    for i in range(5):
        runtime.start_execution(agent_id=agent.id, objective=f"obj-{i}", db=seeded_db)

    page1 = viewer_client.get("/api/audit", params={"limit": 2, "offset": 0}).json()
    page2 = viewer_client.get("/api/audit", params={"limit": 2, "offset": 2}).json()
    assert len(page1) == 2
    assert len(page2) == 2
    assert {e["id"] for e in page1}.isdisjoint({e["id"] for e in page2})


def test_audit_executions_endpoint_orders_by_sequence(viewer_client, seeded_db):
    agent = _agent(seeded_db, "support-agent")
    start = runtime.start_execution(
        agent_id=agent.id,
        objective="Investigate duplicate payment for CUST-1001 and refund the duplicate",
        db=seeded_db,
    )
    execution_id = uuid.UUID(start.execution_id)
    runtime.step(execution_id, seeded_db)
    runtime.step(execution_id, seeded_db)

    response = viewer_client.get(f"/api/audit/executions/{execution_id}")
    assert response.status_code == 200
    events = response.json()
    sequences = [e["sequence"] for e in events]
    assert sequences == list(range(1, len(sequences) + 1))
