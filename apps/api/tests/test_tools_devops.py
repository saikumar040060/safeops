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
    result = tool_registry.get("read_logs").execute(
        {"service_name": "does-not-exist"}, seeded_db
    )

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
