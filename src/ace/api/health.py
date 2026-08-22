from typing import Any

import psycopg
import redis
from fastapi import APIRouter, Response

from ace.config import settings

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready(response: Response) -> dict[str, Any]:
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

    status_msg = "ready" if postgres_status == "up" and redis_status == "up" else "not_ready"
    if status_msg == "not_ready":
        response.status_code = 503

    return {
        "status": status_msg,
        "dependencies": {"postgres": postgres_status, "redis": redis_status},
        "pipeline_lag_seconds": None,
        "bypass_active": False,
    }
