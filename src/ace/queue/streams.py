import logging
import uuid

import redis

from ace.config import settings

logger = logging.getLogger(__name__)


def get_redis_client() -> redis.Redis:
    return redis.from_url(settings.REDIS_URL, socket_connect_timeout=1)


def publish_to_stream(alert_id: uuid.UUID, stream_name: str = "alerts.raw") -> bool:
    """
    Publish an alert ID to the specified Redis Stream.
    Returns True on success, False if Redis is unavailable.
    """
    try:
        client = get_redis_client()
        # Redis streams require dict[str, str|bytes]
        client.xadd(stream_name, {"alert_id": str(alert_id)})
        return True
    except redis.RedisError as e:
        logger.warning(f"Failed to publish alert {alert_id} to stream {stream_name}: {e}")
        return False
