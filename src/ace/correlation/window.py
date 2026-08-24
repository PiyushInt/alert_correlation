import time
import uuid

import redis

from ace.config import settings


def add_open_incident(r: redis.Redis, incident_id: uuid.UUID) -> None:
    """
    Adds an incident to the correlation window.
    The score is the expiration timestamp.
    """
    expiry_time = time.time() + settings.CORRELATION_WINDOW
    r.zadd("ace_open_incidents", {str(incident_id): expiry_time})


def remove_open_incident(r: redis.Redis, incident_id: uuid.UUID) -> None:
    """
    Removes an incident from the correlation window (e.g. when auto-resolved).
    """
    r.zrem("ace_open_incidents", str(incident_id))


def get_open_incidents(r: redis.Redis) -> list[uuid.UUID]:
    """
    Retrieves the list of currently open incidents, purging expired ones first.
    """
    now = time.time()
    # Purge expired incidents
    r.zremrangebyscore("ace_open_incidents", "-inf", now)

    # Get remaining active incidents
    incident_ids_bytes = r.zrange("ace_open_incidents", 0, -1)
    return [
        uuid.UUID(uid.decode("utf-8") if isinstance(uid, bytes) else str(uid))
        for uid in incident_ids_bytes
    ]
