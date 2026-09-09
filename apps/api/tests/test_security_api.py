import uuid

from app.models import Agent
from app.services.agent_runtime import AgentRuntime

runtime = AgentRuntime()


def _agent(db, name) -> Agent:
    return db.query(Agent).filter_by(name=name).one()


def _run_malicious_ticket(db):
    agent = _agent(db, "support-agent")
    start = runtime.start_execution(
        agent_id=agent.id, objective="Investigate support ticket TCK-4837", db=db
    )
    execution_id = uuid.UUID(start.execution_id)
    runtime.step(execution_id, db)
    runtime.step(execution_id, db)
    return execution_id


def test_security_incidents_empty_baseline(viewer_client):
    response = viewer_client.get("/api/security/incidents")
    assert response.status_code == 200
    assert response.json() == []


def test_malicious_ticket_produces_critical_incident(viewer_client, seeded_db):
    execution_id = _run_malicious_ticket(seeded_db)

    response = viewer_client.get("/api/security/incidents")
    assert response.status_code == 200
    incidents = response.json()
    assert len(incidents) == 1
    incident = incidents[0]
    assert incident["severity"] == "CRITICAL"
    assert incident["status"] == "OPEN"
    assert incident["execution_id"] == str(execution_id)
    assert "Ignore all previous instructions" not in incident["description"]


def test_security_incidents_filter_by_severity(viewer_client, seeded_db):
    _run_malicious_ticket(seeded_db)

    critical = viewer_client.get("/api/security/incidents", params={"severity": "CRITICAL"}).json()
    low = viewer_client.get("/api/security/incidents", params={"severity": "LOW"}).json()
    assert len(critical) == 1
    assert low == []


def test_security_incident_detail(viewer_client, seeded_db):
    _run_malicious_ticket(seeded_db)
    incident_id = viewer_client.get("/api/security/incidents").json()[0]["id"]

    response = viewer_client.get(f"/api/security/incidents/{incident_id}")
    assert response.status_code == 200
    assert response.json()["id"] == incident_id


def test_security_incident_unknown_id_returns_404(viewer_client):
    response = viewer_client.get(f"/api/security/incidents/{uuid.uuid4()}")
    assert response.status_code == 404
