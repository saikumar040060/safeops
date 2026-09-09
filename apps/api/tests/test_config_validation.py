import pytest

from app.core.config import (
    _DEV_DEFAULT_DATABASE_URL,
    ConfigurationError,
    Settings,
    validate_production_safety,
)


def _prod_settings(**overrides) -> Settings:
    defaults = dict(
        environment="production",
        demo_mode=False,
        database_url="postgresql+psycopg2://real:real@prod-db.internal:5432/safeops",
        cors_origins=["https://ops.example.com"],
        bootstrap_admin_token="a" * 40,
    )
    defaults.update(overrides)
    return Settings(**defaults)


def test_development_settings_never_validated():
    settings = Settings(environment="development", demo_mode=True)
    validate_production_safety(settings)  # must not raise regardless of demo_mode


def test_production_with_safe_config_starts():
    validate_production_safety(_prod_settings())  # must not raise


def test_production_refuses_demo_mode():
    with pytest.raises(ConfigurationError, match="SAFEOPS_DEMO_MODE"):
        validate_production_safety(_prod_settings(demo_mode=True))


def test_production_refuses_wildcard_cors():
    with pytest.raises(ConfigurationError, match="CORS_ORIGINS"):
        validate_production_safety(_prod_settings(cors_origins=["*"]))


def test_production_refuses_empty_cors():
    with pytest.raises(ConfigurationError, match="CORS_ORIGINS"):
        validate_production_safety(_prod_settings(cors_origins=[]))


def test_production_refuses_dev_default_database_url():
    with pytest.raises(ConfigurationError, match="DATABASE_URL"):
        validate_production_safety(_prod_settings(database_url=_DEV_DEFAULT_DATABASE_URL))


def test_production_refuses_missing_bootstrap_token():
    with pytest.raises(ConfigurationError, match="BOOTSTRAP_ADMIN_TOKEN"):
        validate_production_safety(_prod_settings(bootstrap_admin_token=None))


def test_production_refuses_short_bootstrap_token():
    with pytest.raises(ConfigurationError, match="BOOTSTRAP_ADMIN_TOKEN"):
        validate_production_safety(_prod_settings(bootstrap_admin_token="short"))


@pytest.mark.parametrize(
    "placeholder",
    ["changeme", "change-me-please-change-me-please", "your-secret-token-goes-here-please"],
)
def test_production_refuses_placeholder_bootstrap_token(placeholder):
    with pytest.raises(ConfigurationError, match="BOOTSTRAP_ADMIN_TOKEN"):
        validate_production_safety(_prod_settings(bootstrap_admin_token=placeholder))


def test_invalid_environment_value_rejected():
    with pytest.raises(ValueError):
        Settings(environment="staging")
