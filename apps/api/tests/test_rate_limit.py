"""Milestone 10 sections 6/20: rate limiting."""

import uuid

import pytest
from fastapi import HTTPException

from app.core.rate_limit import rate_limit, reset_all
from app.models import Agent


@pytest.fixture(autouse=True)
def _clean_buckets():
    reset_all()
    yield
    reset_all()


def test_normal_requests_are_allowed():
    identity = uuid.uuid4()
    for _ in range(5):
        rate_limit("test_bucket", identity, max_requests=10, window_seconds=60)


def test_excessive_requests_are_throttled():
    identity = uuid.uuid4()
    for _ in range(5):
        rate_limit("test_bucket", identity, max_requests=5, window_seconds=60)
    with pytest.raises(HTTPException) as exc_info:
        rate_limit("test_bucket", identity, max_requests=5, window_seconds=60)
    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["code"] == "RATE_LIMITED"


def test_different_identities_have_independent_buckets():
    a, b = uuid.uuid4(), uuid.uuid4()
    for _ in range(5):
        rate_limit("test_bucket", a, max_requests=5, window_seconds=60)
    # b's bucket is untouched by a's usage.
    rate_limit("test_bucket", b, max_requests=5, window_seconds=60)


def test_different_buckets_for_same_identity_are_independent():
    identity = uuid.uuid4()
    for _ in range(5):
        rate_limit("bucket_one", identity, max_requests=5, window_seconds=60)
    rate_limit("bucket_two", identity, max_requests=5, window_seconds=60)


def test_window_expiry_allows_requests_again(monkeypatch):
    import app.core.rate_limit as rl_module

    fake_now = [1000.0]
    monkeypatch.setattr(rl_module.time, "monotonic", lambda: fake_now[0])

    identity = uuid.uuid4()
    for _ in range(3):
        rate_limit("test_bucket", identity, max_requests=3, window_seconds=10)
    with pytest.raises(HTTPException):
        rate_limit("test_bucket", identity, max_requests=3, window_seconds=10)

    fake_now[0] += 11  # past the window
    rate_limit("test_bucket", identity, max_requests=3, window_seconds=10)  # must not raise


def test_limiter_cannot_be_bypassed_by_headers_since_it_never_reads_them():
    # The limiter is keyed purely by the identity value the caller passes
    # (always the authenticated operator id at call sites) -- it has no
    # header-reading code path at all, so no malformed/spoofed header can
    # influence which bucket a request lands in.
    import inspect

    from app.core import rate_limit as rl_module

    source = inspect.getsource(rl_module.rate_limit)
    assert "headers" not in source
    assert "request" not in source.lower().replace("requests", "")


def test_execution_create_endpoint_is_rate_limited(client, seeded_db):
    agent = seeded_db.query(Agent).filter_by(name="devops-agent").one()
    headers = {"Authorization": "Bearer sfops_demo_operator_runexec"}

    last_status = None
    for _ in range(25):
        resp = client.post(
            "/api/executions",
            json={
                "agent_id": str(agent.id),
                "objective": "Deploy checkout-service version 1.0 to staging",
            },
            headers=headers,
        )
        last_status = resp.status_code
        if last_status == 429:
            break

    assert last_status == 429
    body = resp.json()
    assert body["detail"]["code"] == "RATE_LIMITED"
    # Safe response: no stack trace, no internals.
    assert "Traceback" not in str(body)


def test_rate_limit_response_not_affected_by_spoofed_headers(client, seeded_db):
    agent = seeded_db.query(Agent).filter_by(name="devops-agent").one()
    headers = {"Authorization": "Bearer sfops_demo_operator_runexec"}

    statuses = []
    for i in range(25):
        resp = client.post(
            "/api/executions",
            json={
                "agent_id": str(agent.id),
                "objective": "Deploy checkout-service version 1.0 to staging",
            },
            headers={**headers, "X-Forwarded-For": f"10.0.0.{i}"},
        )
        statuses.append(resp.status_code)
        if resp.status_code == 429:
            break

    # Varying an attacker-controlled header per request did not let the
    # same authenticated operator dodge the limit.
    assert 429 in statuses
