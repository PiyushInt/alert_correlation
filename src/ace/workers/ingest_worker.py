import logging
import socket
import time
import uuid

import redis

from ace.api.dependencies import SessionLocal
from ace.config import settings
from ace.db.models.alerts import Alert
from ace.ingestion.models import NormalisedAlert
from ace.metrics import registry
from ace.pipeline.damping import check_damping
from ace.pipeline.dedup import check_dedup
from ace.pipeline.fingerprint import compute_fingerprint
from ace.queue.consumer import (
    ack_message,
    dead_letter,
    ensure_consumer_group,
    read_batch,
    reclaim_pending,
)
from ace.queue.streams import get_redis_client, publish_to_stream

logger = logging.getLogger(__name__)


def process_message(r: redis.Redis, message_id: str, alert_id: str) -> bool:
    """Processes a single alert ID from the raw stream."""
    try:
        parsed_id = uuid.UUID(alert_id)
    except ValueError:
        logger.error(f"Invalid alert_id '{alert_id}' in message {message_id}")
        return False

    with SessionLocal() as db:
        alert_row = db.query(Alert).filter(Alert.id == parsed_id).first()
        if not alert_row:
            logger.error(f"Alert {alert_id} not found in database for message {message_id}")
            return False

        alert = NormalisedAlert(
            id=alert_row.id,
            source_tool=alert_row.source_tool,
            external_id=alert_row.external_id,
            severity=alert_row.severity,
            component_id=alert_row.component_id,
            component_unresolved=alert_row.component_unresolved,
            labels=alert_row.labels,
            annotations=alert_row.annotations,
            raw_payload=alert_row.raw_payload,
            starts_at=alert_row.starts_at,
            ends_at=alert_row.ends_at,
            status=alert_row.status,
            environment=alert_row.environment,
            tenant=alert_row.tenant,
        )

        registry.inc_counter("worker_received")

        # 1. Fingerprint
        comp_id_str = str(alert.component_id) if alert.component_id else None
        fingerprint = compute_fingerprint(
            alert.source_tool, comp_id_str, alert.labels.get("alertname", ""), alert.labels
        )

        # Store fingerprint for reference
        alert_row.fingerprint = fingerprint
        db.commit()

        # 2. Damping
        damping_result = check_damping(r, fingerprint, alert.status)

        # 3. Dedup
        is_duplicate = check_dedup(r, fingerprint, alert, db)

        if is_duplicate:
            # Duplicate was dropped
            return True

        # 4. Forward
        if damping_result.forward_to_clean:
            # Publish to alerts.clean
            success = publish_to_stream(parsed_id, stream_name="alerts.clean")
            if success:
                registry.inc_counter("worker_forwarded")
            else:
                return False

        return True


def run_worker() -> None:
    logger.info("Starting ingest worker...")
    r = get_redis_client()

    stream_name = "alerts.raw"
    group_name = settings.CONSUMER_GROUP
    consumer_name = f"ingest-{socket.gethostname()}-{uuid.uuid4().hex[:6]}"

    # Wait for Redis if necessary
    while True:
        try:
            r.ping()
            break
        except redis.RedisError:
            logger.warning("Waiting for Redis...")
            time.sleep(2)

    ensure_consumer_group(r, stream_name, group_name)

    # Dictionary to track retries per message_id
    retries: dict[str, int] = {}
    last_reclaim = time.time()

    while True:
        try:
            # Reclaim pending entries periodically
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
                        registry.inc_counter("worker_dead_lettered")
                        ack_message(r, stream_name, group_name, msg.message_id)
                        del retries[msg.message_id]
                    else:
                        logger.warning(
                            f"Message {msg.message_id} processing failed. "
                            f"Retry {retries[msg.message_id]}/{settings.MAX_CONSUMER_RETRIES}"
                        )
                        # Minimal backoff for retries
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
