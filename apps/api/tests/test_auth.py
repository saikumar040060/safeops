from app.core.security import ROLE_PERMISSIONS, generate_token, hash_token
from app.models.enums import OperatorRole


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_unauthenticated_request_to_protected_endpoint_is_401(client):
    resp = client.get("/api/agents")
    assert resp.status_code == 401
    assert resp.json()["detail"]["code"] == "UNAUTHENTICATED"


def test_missing_bearer_scheme_is_401(client):
    resp = client.get("/api/agents", headers={"Authorization": "sfops_demo_admin_allaccess"})
    assert resp.status_code == 401


def test_malformed_auth_header_is_401(client):
    resp = client.get("/api/agents", headers={"Authorization": "Bearer"})
    assert resp.status_code == 401


def test_unknown_token_is_401(client):
    resp = client.get("/api/agents", headers=_auth("sfops_this_token_does_not_exist"))
    assert resp.status_code == 401


def test_valid_demo_token_authenticates(client):
    resp = client.get("/api/auth/me", headers=_auth("sfops_demo_viewer_readonly"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["role"] == "VIEWER"
    assert body["username"] == "viewer-demo"


def test_viewer_can_read(client):
    resp = client.get("/api/agents", headers=_auth("sfops_demo_viewer_readonly"))
    assert resp.status_code == 200


def test_public_config_endpoint_requires_no_auth(client):
    resp = client.get("/api/auth/config")
    assert resp.status_code == 200
    assert resp.json()["demo_mode"] is True


def test_health_endpoint_requires_no_auth(client):
    assert client.get("/api/health").status_code == 200


def test_revoked_token_rejected(client, seeded_db):
    from sqlalchemy import select

    from app.models import OperatorToken

    token_row = seeded_db.scalar(
        select(OperatorToken).where(
            OperatorToken.token_hash == hash_token("sfops_demo_viewer_readonly")
        )
    )
    from datetime import UTC, datetime

    token_row.revoked_at = datetime.now(UTC)
    seeded_db.commit()

    resp = client.get("/api/agents", headers=_auth("sfops_demo_viewer_readonly"))
    assert resp.status_code == 401


def test_expired_token_rejected(client, seeded_db):
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select

    from app.core.security import issue_token
    from app.models import Operator

    operator = seeded_db.scalar(select(Operator).where(Operator.username == "operator-demo"))
    token, raw = issue_token(
        operator, raw_token=generate_token(), expires_at=datetime.now(UTC) - timedelta(minutes=1)
    )
    seeded_db.add(token)
    seeded_db.commit()

    resp = client.get("/api/agents", headers=_auth(raw))
    assert resp.status_code == 401


def test_inactive_operator_rejected(client, seeded_db):
    from sqlalchemy import select

    from app.models import Operator

    operator = seeded_db.scalar(select(Operator).where(Operator.username == "admin-demo"))
    operator.is_active = False
    seeded_db.commit()

    resp = client.get("/api/agents", headers=_auth("sfops_demo_admin_allaccess"))
    assert resp.status_code == 401


def test_role_permission_matrix_matches_spec():
    assert ROLE_PERMISSIONS[OperatorRole.VIEWER] == {"read"}
    assert ROLE_PERMISSIONS[OperatorRole.OPERATOR] == {"read", "execute"}
    assert ROLE_PERMISSIONS[OperatorRole.APPROVER] == {"read", "approve"}
    assert ROLE_PERMISSIONS[OperatorRole.ADMIN] == {"read", "execute", "approve"}


def test_token_hash_is_deterministic_and_one_way():
    raw = generate_token()
    assert hash_token(raw) == hash_token(raw)
    assert hash_token(raw) != raw


def test_concurrent_bootstrap_admin_creates_exactly_one_operator_and_token(db_engine, db_session):
    # Uses the unseeded db_session (not seeded_db) -- seed() already
    # creates an ADMIN demo operator, which would make
    # ensure_bootstrap_admin() correctly no-op immediately rather than
    # exercising the race this test targets.
    # `uvicorn --workers N` runs N separate processes, each running its own
    # lifespan startup independently -- ensure_bootstrap_admin() must be
    # safe when several of them race to provision the same bootstrap admin
    # at once (this crashed container startup entirely before the fix: an
    # unhandled IntegrityError on the second worker's insert).
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from sqlalchemy.orm import Session

    from app.core.config import Settings
    from app.core.security import ensure_bootstrap_admin
    from app.models import Operator, OperatorToken

    settings = Settings(
        bootstrap_admin_token="a-fixed-bootstrap-token-used-by-every-worker-1234",
        bootstrap_admin_username="race-admin",
    )
    barrier = Barrier(8)

    def call_bootstrap():
        with Session(db_engine) as session:
            barrier.wait(timeout=5)
            ensure_bootstrap_admin(session, settings)

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda _: call_bootstrap(), range(8)))

    operators = db_session.query(Operator).filter_by(username="race-admin").all()
    assert len(operators) == 1
    tokens = db_session.query(OperatorToken).filter_by(operator_id=operators[0].id).all()
    assert len(tokens) == 1
