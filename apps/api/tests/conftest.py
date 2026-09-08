import os
from urllib.parse import urlsplit, urlunsplit

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

import app.models  # noqa: F401  (registers models on Base.metadata)
from app.core.config import get_settings
from app.core.database import Base
from app.core.seed import seed


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
    from fastapi.testclient import TestClient

    from app.core.database import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: seeded_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)
