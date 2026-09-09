"""Milestone 10 section 9/21: deploy_staging/deploy_production idempotency."""

from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import Session

from app.models import Deployment, Service
from app.models.enums import DeploymentEnvironment
from app.tools.devops import DeployProductionTool


def _service(db) -> Service:
    return db.query(Service).filter_by(name="checkout-service").one()


def test_retry_with_same_idempotency_key_does_not_duplicate(seeded_db):
    tool = DeployProductionTool()
    args = {"service_name": "checkout-service", "version": "3.0", "idempotency_key": "fixed-key-1"}

    first = tool.execute(args, seeded_db)
    second = tool.execute(args, seeded_db)

    assert first.success and second.success
    assert first.data == second.data

    count = (
        seeded_db.query(Deployment)
        .filter_by(environment=DeploymentEnvironment.PRODUCTION, version="3.0")
        .count()
    )
    assert count == 1


def test_different_version_with_different_key_creates_new_row(seeded_db):
    tool = DeployProductionTool()
    tool.execute(
        {"service_name": "checkout-service", "version": "3.1", "idempotency_key": "key-a"},
        seeded_db,
    )
    tool.execute(
        {"service_name": "checkout-service", "version": "3.2", "idempotency_key": "key-b"},
        seeded_db,
    )

    versions = {
        d.version
        for d in seeded_db.query(Deployment).filter(Deployment.version.in_(["3.1", "3.2"])).all()
    }
    assert versions == {"3.1", "3.2"}


def test_no_idempotency_key_behaves_as_before(seeded_db):
    tool = DeployProductionTool()
    result = tool.execute({"service_name": "checkout-service", "version": "3.3"}, seeded_db)
    assert result.success
    assert result.data["version"] == "3.3"


def test_concurrent_same_key_executes_exactly_once(db_engine, seeded_db):
    from threading import Barrier

    barrier = Barrier(5)

    def call_deploy():
        with Session(db_engine) as session:
            tool = DeployProductionTool()
            barrier.wait(timeout=5)
            return tool.execute(
                {
                    "service_name": "checkout-service",
                    "version": "3.4",
                    "idempotency_key": "concurrent-key",
                },
                session,
            )

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(lambda _: call_deploy(), range(5)))

    assert all(r.success for r in results)
    deployed_ats = {r.data["deployed_at"] for r in results}
    assert len(deployed_ats) == 1  # every caller got back the same row

    with Session(db_engine) as session:
        count = session.query(Deployment).filter_by(version="3.4").count()
        assert count == 1
