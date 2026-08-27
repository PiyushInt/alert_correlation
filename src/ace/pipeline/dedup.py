import logging

import redis
from sqlalchemy.orm import Session

from ace.config import settings
from ace.db.models.alerts import Alert
from ace.ingestion.models import NormalisedAlert
from ace.metrics import registry

logger = logging.getLogger(__name__)


def check_dedup(
    r: redis.Redis,
    fingerprint: str,
    incoming_alert: NormalisedAlert,
    db: Session,
) -> bool:
    """
    Checks if an alert is a duplicate.
    Returns True if it's a duplicate (should be dropped).
    Returns False if it's new (should be forwarded).

    - If firing hit: update occurrence_count and severity on original, drop.
    - If resolved hit: update original's status/ends_at, link incoming via
      resolves_alert_id, delete dedup key (avoids re-fire bug), and forward incoming.
    """
    dedup_key = f"dedup:{fingerprint}"

    stored_val = r.get(dedup_key)

    if incoming_alert.status == "firing":
        if stored_val:
            # Hit!
            original_id = (
                stored_val.decode("utf-8") if isinstance(stored_val, bytes) else str(stored_val)
            )
            original_alert = db.query(Alert).filter(Alert.id == original_id).first()
            if original_alert:
                original_alert.occurrence_count += 1

                # Update last_seen_at to reflect latest occurrence
                incoming_db_alert = db.query(Alert).filter(Alert.id == incoming_alert.id).first()
                if incoming_db_alert:
                    original_alert.last_seen_at = incoming_db_alert.received_at

                db.commit()
                registry.inc_counter("worker_deduped")
                return True
            else:
                logger.warning(f"Dedup hit for {fingerprint} but original {original_id} not in DB")

        # Miss
        r.set(dedup_key, str(incoming_alert.id), ex=settings.DEDUP_WINDOW)
        return False

    else:
        # Resolved
        if stored_val:
            original_id = (
                stored_val.decode("utf-8") if isinstance(stored_val, bytes) else str(stored_val)
            )
            r.delete(dedup_key)  # Prevent re-fire bug

            original_alert = db.query(Alert).filter(Alert.id == original_id).first()
            if original_alert:
                # Link the incoming resolved alert to the firing one
                incoming_db_alert = db.query(Alert).filter(Alert.id == incoming_alert.id).first()
                if incoming_db_alert:
                    incoming_db_alert.resolves_alert_id = original_alert.id

                db.commit()

        # Always forward resolved alerts
        return False
