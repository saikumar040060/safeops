"""Milestone 10 section 11/14/15: readiness, error model, request IDs."""


def test_ready_endpoint_reports_healthy_with_no_auth(client):
    resp = client.get("/api/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ready"] is True
    assert body["checks"]["database_reachable"] is True
    assert body["checks"]["required_tables_accessible"] is True
    assert body["checks"]["configuration_valid"] is True
    # Never leaks a connection string, credentials, or any other secret.
    assert "safeops:safeops" not in str(body)
    assert "postgresql" not in str(body)


def test_ready_response_has_no_secrets_or_internals(client):
    resp = client.get("/api/ready")
    body_text = str(resp.json())
    for forbidden in ("password", "DATABASE_URL", "Traceback"):
        assert forbidden not in body_text


def test_request_id_echoed_in_response_header(client):
    resp = client.get("/api/health")
    assert "X-Request-ID" in resp.headers
    assert len(resp.headers["X-Request-ID"]) > 0


def test_caller_supplied_safe_request_id_is_honored(client):
    resp = client.get("/api/health", headers={"X-Request-ID": "my-safe-id-123"})
    assert resp.headers["X-Request-ID"] == "my-safe-id-123"


def test_unsafe_request_id_header_is_replaced(client):
    malicious = "not safe\r\nX-Injected: evil"
    resp = client.get("/api/health", headers={"X-Request-ID": malicious})
    assert resp.headers["X-Request-ID"] != malicious
    assert "\r" not in resp.headers["X-Request-ID"]


def test_401_error_body_includes_request_id():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as anon_client:
        resp = anon_client.get("/api/agents")
        assert resp.status_code == 401
        detail = resp.json()["detail"]
        assert detail["code"] == "UNAUTHENTICATED"
        assert "request_id" in detail
        assert len(detail["request_id"]) > 0


def test_validation_error_does_not_leak_internals(client):
    resp = client.post(
        "/api/executions",
        json={"agent_id": "not-a-uuid"},
        headers={"Authorization": "Bearer sfops_demo_operator_runexec"},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["detail"]["code"] == "VALIDATION_ERROR"
    assert "request_id" in body["detail"]
    body_text = str(body)
    assert "Traceback" not in body_text
    assert "pydantic_core" not in body_text


def test_404_plain_detail_still_works_unchanged(client):
    import uuid

    resp = client.get(
        f"/api/executions/{uuid.uuid4()}",
        headers={"Authorization": "Bearer sfops_demo_viewer_readonly"},
    )
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Execution not found"}


def test_metrics_endpoint_requires_auth(client):
    assert client.get("/api/metrics").status_code == 401


def test_metrics_endpoint_returns_safe_counters(client):
    resp = client.get(
        "/api/metrics", headers={"Authorization": "Bearer sfops_demo_viewer_readonly"}
    )
    assert resp.status_code == 200
    body = resp.json()
    for key in (
        "executions_started_total",
        "executions_blocked_total",
        "approvals_pending",
        "risk_blocks_total",
        "security_incidents_open",
        "tool_failures_total",
        "request_latency",
    ):
        assert key in body


def test_security_headers_present_on_every_response(client):
    resp = client.get("/api/health")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Referrer-Policy"] == "no-referrer"
    assert "Content-Security-Policy" in resp.headers
    # No HSTS in development -- this process cannot itself guarantee HTTPS.
    assert "Strict-Transport-Security" not in resp.headers
