from typing import Any

import psycopg
import redis
from fastapi import APIRouter

from ace.config import settings

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready() -> dict[str, Any]:
    # Check Postgres
    postgres_status = "down"
    try:
        with psycopg.connect(settings.DATABASE_URL.replace("+psycopg", "")) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                postgres_status = "up"
    except Exception:
        pass

    # Check Redis
    redis_status = "down"
    try:
        r = redis.from_url(settings.REDIS_URL, socket_connect_timeout=1)
        if r.ping():
            redis_status = "up"
    except Exception:
        pass

    return {
        "status": "ready" if postgres_status == "up" and redis_status == "up" else "not_ready",
        "dependencies": {"postgres": postgres_status, "redis": redis_status},
        "pipeline_lag_seconds": None,
        "bypass_active": False,
    }
