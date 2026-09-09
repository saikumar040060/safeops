import uuid
from datetime import UTC, datetime

from app.models import Deployment, Service
from app.models.enums import DeploymentEnvironment
from app.tools import tool_registry


def test_read_logs_returns_seeded_entries(seeded_db):
    result = tool_registry.get("read_logs").execute(
        {"service_name": "checkout-service", "limit": 3}, seeded_db
    )

    assert result.success is True
    assert len(result.data["logs"]) == 3
    # most recent first
    timestamps = [log["timestamp"] for log in result.data["logs"]]
    assert timestamps == sorted(timestamps, reverse=True)


def test_read_logs_unknown_service(seeded_db):
    result = tool_registry.get("read_logs").execute({"service_name": "does-not-exist"}, seeded_db)

    assert result.success is False
    assert result.error.code == "NOT_FOUND"


def test_get_deployment_returns_current_state(seeded_db):
    result = tool_registry.get("get_deployment").execute(
        {"service_name": "checkout-service"}, seeded_db
    )

    assert result.success is True
    assert result.data["staging"]["version"] == "1.5.0-rc1"
    assert result.data["production"]["version"] == "1.4.2"


def test_deploy_staging_changes_state(seeded_db):
    deploy = tool_registry.get("deploy_staging")
    get_deployment = tool_registry.get("get_deployment")

    result = deploy.execute({"service_name": "checkout-service", "version": "1.6.0"}, seeded_db)
    assert result.success is True
    assert result.data["environment"] == "STAGING"
    assert result.data["version"] == "1.6.0"

    state = get_deployment.execute({"service_name": "checkout-service"}, seeded_db)
    assert state.data["staging"]["version"] == "1.6.0"
    assert state.data["production"]["version"] == "1.4.2"


def test_deploy_production_changes_state(seeded_db):
    deploy = tool_registry.get("deploy_production")
    get_deployment = tool_registry.get("get_deployment")

    result = deploy.execute({"service_name": "checkout-service", "version": "1.5.0"}, seeded_db)
    assert result.success is True
    assert result.data["environment"] == "PRODUCTION"
    assert result.data["version"] == "1.5.0"

    state = get_deployment.execute({"service_name": "checkout-service"}, seeded_db)
    assert state.data["production"]["version"] == "1.5.0"
    assert state.data["staging"]["version"] == "1.5.0-rc1"


def test_get_deployment_breaks_timestamp_ties_by_id(seeded_db):
    service = seeded_db.query(Service).filter_by(name="checkout-service").one()
    deployed_at = datetime(2100, 1, 1, tzinfo=UTC)
    lower_id = uuid.UUID(int=1)
    higher_id = uuid.UUID(int=2)
    seeded_db.add_all(
        [
            Deployment(
                id=lower_id,
                service_id=service.id,
                environment=DeploymentEnvironment.STAGING,
                version="tie-lower-id",
                deployed_at=deployed_at,
            ),
            Deployment(
                id=higher_id,
                service_id=service.id,
                environment=DeploymentEnvironment.STAGING,
                version="tie-higher-id",
                deployed_at=deployed_at,
            ),
        ]
    )
    seeded_db.commit()

    result = tool_registry.get("get_deployment").execute(
        {"service_name": "checkout-service"}, seeded_db
    )

    assert result.success is True
    assert result.data["staging"]["version"] == "tie-higher-id"
