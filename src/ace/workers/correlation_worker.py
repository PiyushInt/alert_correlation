import logging
import socket
import time
import uuid

import redis

from ace.api.deps import SessionLocal
from ace.config import settings
from ace.correlation.engine import process_alert_correlation
from ace.db.models.alerts import Alert
from ace.queue.consumer import (
    ack_message,
    dead_letter,
    ensure_consumer_group,
    read_batch,
    reclaim_pending,
)
from ace.queue.streams import get_redis_client

logger = logging.getLogger(__name__)


def process_message(r: redis.Redis, message_id: str, alert_id: str) -> bool:
    """Processes a single alert ID from the clean stream."""
    try:
        parsed_id = uuid.UUID(alert_id)
    except ValueError:
        logger.error(f"Invalid alert_id '{alert_id}' in message {message_id}")
        return False

    with SessionLocal() as db:
        alert = db.query(Alert).filter(Alert.id == parsed_id).first()
        if not alert:
            logger.error(f"Alert {alert_id} not found in database for message {message_id}")
            return False

        # Run Stage 4 Pipeline: Correlation
        process_alert_correlation(db, r, alert)
        return True


def run_worker() -> None:
    logger.info("Starting correlation worker...")
    r = get_redis_client()

    stream_name = "alerts.clean"
    group_name = settings.CORRELATION_GROUP
    consumer_name = f"correlator-{socket.gethostname()}-{uuid.uuid4().hex[:6]}"

    # Wait for Redis
    while True:
        try:
            r.ping()
            break
        except redis.RedisError:
            logger.warning("Waiting for Redis...")
            time.sleep(2)

    ensure_consumer_group(r, stream_name, group_name)

    retries: dict[str, int] = {}
    last_reclaim = time.time()

    while True:
        try:
            now = time.time()
            if (now - last_reclaim) * 1000 > settings.CONSUMER_RECLAIM_IDLE_MS:
                reclaimed = reclaim_pending(
                    r,
                    stream_name,
                    group_name,
                    consumer_name,
                    settings.CONSUMER_RECLAIM_IDLE_MS,
                    count=settings.CONSUMER_BATCH_SIZE,
                )
                messages = reclaimed
                last_reclaim = now
            else:
                messages = read_batch(
                    r,
                    stream_name,
                    group_name,
                    consumer_name,
                    settings.CONSUMER_BATCH_SIZE,
                    settings.CONSUMER_BLOCK_MS,
                )

            for msg in messages:
                alert_id = msg.data.get("alert_id")
                if not alert_id:
                    logger.error(f"Message {msg.message_id} missing alert_id. Dead-lettering.")
                    dead_letter(r, msg)
                    ack_message(r, stream_name, group_name, msg.message_id)
                    continue

                success = False
                try:
                    success = process_message(r, msg.message_id, alert_id)
                except Exception as e:
                    logger.exception(f"Unhandled exception processing {msg.message_id}: {e}")

                if success:
                    ack_message(r, stream_name, group_name, msg.message_id)
                    if msg.message_id in retries:
                        del retries[msg.message_id]
                else:
                    retries[msg.message_id] = retries.get(msg.message_id, 0) + 1
                    if retries[msg.message_id] >= settings.MAX_CONSUMER_RETRIES:
                        logger.error(
                            f"Message {msg.message_id} failed {settings.MAX_CONSUMER_RETRIES} "
                            "times. Dead-lettering."
                        )
                        dead_letter(r, msg)
                        ack_message(r, stream_name, group_name, msg.message_id)
                        del retries[msg.message_id]
                    else:
                        logger.warning(
                            f"Message {msg.message_id} processing failed. "
                            f"Retry {retries[msg.message_id]}/{settings.MAX_CONSUMER_RETRIES}"
                        )
                        time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Worker stopped by user.")
            break
        except Exception as e:
            logger.error(f"Worker loop error: {e}")
            time.sleep(2)


if __name__ == "__main__":
    from ace.logging import setup_logging

    setup_logging()
    run_worker()
