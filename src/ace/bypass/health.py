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
    doesn't exist, or if the stream doesn't exist.
    Lag is the age of the oldest unread entry (either pending or undelivered).
    """
    try:
        groups = r.xinfo_groups("alerts.raw")
        last_delivered_id = None
        for g in groups:
            g_name = g["name"].decode("utf-8") if isinstance(g["name"], bytes) else str(g["name"])
            if g_name == settings.CONSUMER_GROUP:
                last_delivered_id = g.get("last-delivered-id")
                if isinstance(last_delivered_id, bytes):
                    last_delivered_id = last_delivered_id.decode("utf-8")
                break

        if last_delivered_id is None:
            return None

        # 1. Check PEL
        pending = r.xpending("alerts.raw", settings.CONSUMER_GROUP)
        if pending and pending["pending"] > 0:
            oldest_id = (
                pending["min"].decode("utf-8")
                if isinstance(pending["min"], bytes)
                else str(pending["min"])
            )
            ts_ms = int(oldest_id.split("-")[0])
            lag_seconds = int(datetime.now(UTC).timestamp() - (ts_ms / 1000.0))
            return lag_seconds

        # 2. Check undelivered
        if last_delivered_id:
            # '(' means exclusive
            unread = r.xrange("alerts.raw", f"({last_delivered_id}", "+", count=1)
            if unread:
                first_id = unread[0][0]
                oldest_id = (
                    first_id.decode("utf-8") if isinstance(first_id, bytes) else str(first_id)
                )
                ts_ms = int(oldest_id.split("-")[0])
                return int(datetime.now(UTC).timestamp() - (ts_ms / 1000.0))

        # No pending entries -> no lag
        return 0

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
