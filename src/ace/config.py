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
    CANARY_ENABLED: bool = Field(
        default=False, description="Enable automatic canary runs in lifespan"
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
    FLAP_THRESHOLD: int = Field(default=5, description="Flips within window to trigger suppression")
    FUZZY_MATCH_THRESHOLD: float = Field(
        default=80.0,
        description="Rapidfuzz WRatio score (0-100) below which fuzzy matches are rejected",
    )
    MIN_MAP_COVERAGE: float = Field(
        default=0.7, description="Minimum percentage of alerts needing mapped components"
    )

    # Queue & Worker Settings
    STREAM_MAXLEN: int = Field(default=10000, description="Approximate cap on Redis Streams")
    MAX_CONSUMER_RETRIES: int = Field(default=3, description="Max retries before dead-lettering")
    CONSUMER_GROUP: str = Field(
        default="ace-pipeline", description="Redis stream consumer group name"
    )
    CONSUMER_BATCH_SIZE: int = Field(default=10, description="Max messages per batch")
    CONSUMER_BLOCK_MS: int = Field(
        default=2000, description="Milliseconds to block for new messages"
    )
    CONSUMER_RECLAIM_IDLE_MS: int = Field(
        default=30000, description="Milliseconds before reclaiming pending entries"
    )

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
