import logging
from datetime import UTC, datetime
from typing import Literal

import psycopg
import redis

from ace.bypass import canary
from ace.config import settings
from ace.metrics import registry

logger = logging.getLogger(__name__)

State = Literal["OK", "DEGRADED", "BYPASS"]


def get_pipeline_lag(r: redis.Redis) -> int | None:
    """
    Measures pipeline lag. Returns None ("lag unknown") if the consumer group
    doesn't exist (which is true for Phase 3), or if the stream doesn't exist.
    """
    try:
        groups = r.xinfo_groups("alerts.raw")
        if not groups:
            # No consumer groups exist, lag is unknown
            return None

        # In Phase 5, we will actually compute lag based on the consumer group's PEL
        # or the oldest unread entry.
        return None
    except redis.exceptions.ResponseError as e:
        if "no such key" in str(e).lower():
            return None
        logger.warning(f"Failed to read consumer groups for lag: {e}")
        return None
    except redis.RedisError:
        return None


def evaluate_state() -> tuple[State, int | None]:
    """
    Evaluates system health and returns (State, pipeline_lag_seconds).
    Logs state transitions using the metrics registry.
    """
    reasons = []

    # 1. Check Postgres
    postgres_up = False
    try:
        with psycopg.connect(settings.DATABASE_URL.replace("+psycopg", ""), connect_timeout=1):
            postgres_up = True
    except Exception:
        reasons.append("Postgres down")

    # 2. Check Redis
    redis_up = False
    pipeline_lag = None
    try:
        r = redis.from_url(settings.REDIS_URL, socket_connect_timeout=1)
        if r.ping():
            redis_up = True
            pipeline_lag = get_pipeline_lag(r)
    except Exception:
        reasons.append("Redis down")

    # 3. Check Canary
    canary_fresh = True
    if settings.CANARY_ENABLED and canary.last_canary_time:
        age = (datetime.now(UTC) - canary.last_canary_time).total_seconds()
        if age > settings.CANARY_TIMEOUT:
            canary_fresh = False
            reasons.append(f"Canary stale ({int(age)}s)")

    # 4. Check Pipeline Lag
    lag_exceeded = False
    if pipeline_lag is not None and pipeline_lag > settings.MAX_PIPELINE_LAG:
        lag_exceeded = True
        reasons.append(f"Pipeline lag exceeded ({pipeline_lag}s)")

    # Determine State
    new_state: State = "OK"
    if not postgres_up or not redis_up or not canary_fresh or lag_exceeded:
        new_state = "BYPASS"

    reason_str = ", ".join(reasons) if reasons else "Healthy"
    registry.record_state_transition(new_state, reason_str)

    return new_state, pipeline_lag
