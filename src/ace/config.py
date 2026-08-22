from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Core Application Settings
    APP_NAME: str = "ace"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # Database (Synchronous psycopg)
    DATABASE_URL: str = "postgresql+psycopg://ace_user:ace_password@localhost:5433/ace_db"

    # Redis
    REDIS_URL: str = "redis://localhost:6380/0"

    # Correlation & Pipeline Constants
    MAX_INCIDENT_HOPS: int = Field(
        default=3, description="Maximum graph hops to search for related alerts"
    )
    MAX_INCIDENT_ALERTS: int = Field(
        default=500, description="Size cap for alerts in a single incident to prevent over-merging"
    )
    MAX_PIPELINE_LAG: int = Field(
        default=300,
        description="Maximum permitted seconds of lag before failing open to RAW routing",
    )
    CANARY_INTERVAL: int = Field(default=60, description="Seconds between canary alert injections")
    CANARY_TIMEOUT: int = Field(
        default=120, description="Seconds before canary failure triggers bypass mode"
    )
    CRITICAL_BYPASS_SEVERITY: str = Field(
        default="critical", description="Severity level that bypasses correlation completely"
    )
    CORRELATION_WINDOW: int = Field(default=300, description="Seconds window for alert grouping")
    DEDUP_WINDOW: int = Field(
        default=3600, description="Seconds window for exact duplicate suppression"
    )
    FLAP_WINDOW: int = Field(default=900, description="Seconds window for flapping state detection")
    FUZZY_MATCH_THRESHOLD: float = Field(
        default=0.85, description="String similarity threshold for text clustering"
    )
    MIN_MAP_COVERAGE: float = Field(
        default=0.7, description="Minimum percentage of alerts needing mapped components"
    )

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
