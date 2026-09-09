from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Config values that must never be allowed to reach production -- either
# because they are the literal defaults baked into this file (safe only for
# local dev, where docker-compose.yml provisions the matching credentials),
# or because they are the kind of placeholder a human might paste in and
# forget to change.
_DEV_DEFAULT_DATABASE_URL = "postgresql+psycopg2://safeops:safeops@localhost:5432/safeops"
_PLACEHOLDER_SECRETS = {"changeme", "change-me", "secret", "password", "admin", "test", ""}
_PLACEHOLDER_MARKERS = ("changeme", "change-me", "example", "your-", "generate-a-real", "<", "todo")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", populate_by_name=True)

    app_name: str = "SafeOps API"

    # SAFEOPS_ENV / SAFEOPS_DEMO_MODE are the explicit, milestone-10-mandated
    # names -- kept as distinct aliases (rather than the default
    # case-insensitive ENVIRONMENT/DEMO_MODE matching pydantic-settings would
    # otherwise use) so they read the same in code, .env, and this report.
    environment: str = Field(default="development", validation_alias="SAFEOPS_ENV")
    demo_mode: bool = Field(default=True, validation_alias="SAFEOPS_DEMO_MODE")

    database_url: str = _DEV_DEFAULT_DATABASE_URL
    cors_origins: list[str] = ["http://localhost:3000"]

    max_execution_steps: int = Field(default=25, validation_alias="MAX_EXECUTION_STEPS")
    stepping_lease_ttl_seconds: int = Field(
        default=30, validation_alias="STEPPING_LEASE_TTL_SECONDS"
    )

    # The one secret production needs: seeds the first ADMIN operator/token
    # so there is a way in before any other account exists. Never has a
    # usable default -- see validate_production_safety().
    bootstrap_admin_token: str | None = Field(
        default=None, validation_alias="SAFEOPS_BOOTSTRAP_ADMIN_TOKEN"
    )
    bootstrap_admin_username: str = Field(
        default="admin", validation_alias="SAFEOPS_BOOTSTRAP_ADMIN_USERNAME"
    )

    @field_validator("environment")
    @classmethod
    def _validate_environment(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"development", "production"}:
            raise ValueError(f"SAFEOPS_ENV must be 'development' or 'production', got {value!r}")
        return normalized

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


class ConfigurationError(RuntimeError):
    """Raised at startup when the running configuration is unsafe. Always
    fatal -- the process must not go on to serve traffic."""


def validate_production_safety(settings: Settings) -> None:
    """Fail fast on any configuration that would be unsafe in production.
    Called once at application startup, before the app starts accepting
    requests. Every check here is deliberately conservative: it is far
    better to refuse to start than to silently run an insecure production
    deployment.
    """
    if not settings.is_production:
        return

    errors: list[str] = []

    if settings.demo_mode:
        errors.append(
            "SAFEOPS_DEMO_MODE=true is not allowed when SAFEOPS_ENV=production "
            "(demo mode seeds well-known operator credentials)."
        )

    if not settings.cors_origins or "*" in settings.cors_origins:
        errors.append("CORS_ORIGINS must be an explicit, non-wildcard origin list in production.")

    if settings.database_url == _DEV_DEFAULT_DATABASE_URL:
        errors.append("DATABASE_URL is still the local-dev default; set a real production value.")

    token = settings.bootstrap_admin_token
    normalized_token = (token or "").strip().lower()
    looks_like_placeholder = normalized_token in _PLACEHOLDER_SECRETS or any(
        marker in normalized_token for marker in _PLACEHOLDER_MARKERS
    )
    if not token or looks_like_placeholder or len(token) < 32:
        errors.append(
            "SAFEOPS_BOOTSTRAP_ADMIN_TOKEN must be set to a real secret of at least "
            "32 characters in production (used once to provision the first ADMIN operator)."
        )

    if errors:
        raise ConfigurationError(
            "Refusing to start in production with unsafe configuration: " + "; ".join(errors)
        )
