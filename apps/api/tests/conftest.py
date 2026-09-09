import os
from urllib.parse import urlsplit, urlunsplit

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

import app.models  # noqa: F401  (registers models on Base.metadata)
from app.core.config import get_settings
from app.core.database import Base
from app.core.seed import seed
from app.models import Operator
from app.models.enums import OperatorRole


def make_operator(
    db: Session, username: str = "alice", role: OperatorRole = OperatorRole.APPROVER
) -> Operator:
    """Test helper: get-or-create an Operator for tests that exercise
    service-layer code (e.g. ApprovalEngine) directly rather than through
    the HTTP API. Role-based access is enforced at the API layer
    (app.core.security.require_permission); the service layer trusts
    whatever already-authenticated Operator its caller passes in, so any
    role works here unless a test is specifically checking RBAC."""
    operator = db.query(Operator).filter_by(username=username).one_or_none()
    if operator is None:
        operator = Operator(username=username, display_name=username, role=role)
        db.add(operator)
        db.flush()
    return operator


def _test_database_url() -> str:
    override = os.environ.get("TEST_DATABASE_URL")
    if override:
        return override
    parts = urlsplit(get_settings().database_url)
    return urlunsplit((parts.scheme, parts.netloc, "/safeops_test", parts.query, parts.fragment))


def _ensure_database_exists(url: str) -> None:
    parts = urlsplit(url)
    admin_url = urlunsplit((parts.scheme, parts.netloc, "/postgres", parts.query, parts.fragment))
    db_name = parts.path.lstrip("/")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": db_name}
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{db_name}"'))
    finally:
        admin_engine.dispose()


@pytest.fixture(scope="session")
def db_engine():
    url = _test_database_url()
    _ensure_database_exists(url)
    engine = create_engine(url)
    Base.metadata.create_all(engine)

    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(db_engine):
    with db_engine.connect() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())
        connection.commit()

    with Session(db_engine) as session:
        yield session


@pytest.fixture()
def seeded_db(db_session):
    seed(db_session)
    return db_session


@pytest.fixture()
def client(seeded_db):
    """A bare TestClient with no default Authorization header -- the right
    fixture for anything that specifically exercises authentication itself
    (missing/invalid/expired tokens, 401s). Most other tests that only need
    *some* valid identity to get past RBAC should use `viewer_client`."""
    from fastapi.testclient import TestClient

    from app.core.database import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: seeded_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture()
def viewer_client(client):
    """`client` with a seeded demo VIEWER token attached by default -- for
    tests that exercise read-only endpoint behavior and don't care about
    auth/RBAC specifics, which have their own dedicated tests."""
    client.headers["Authorization"] = "Bearer sfops_demo_viewer_readonly"
    return client
