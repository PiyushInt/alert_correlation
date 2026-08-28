import datetime
import logging

from sqlalchemy.orm import Session

from ace.db.models.incidents import Incident, NotificationLog
from ace.itsm.sync import sync_incident
from ace.notification.render import render_notification
from ace.notification.senders.file import FileSender

logger = logging.getLogger(__name__)


def dispatch_incident_event(db: Session, incident: Incident, event_type: str) -> None:
    # Check idempotency
    exists = (
        db.query(NotificationLog)
        .filter(
            NotificationLog.incident_id == incident.id, NotificationLog.event_type == event_type
        )
        .first()
    )

    if exists:
        logger.info(f"Skipping dispatch for {incident.id} event {event_type} (already dispatched)")
        return

    logger.info(f"Dispatching notification for {incident.id} ({event_type})")

    # Render payload
    payload = render_notification(db, incident, event_type)

    # Send
    sender = FileSender()
    sender.send(str(incident.id), payload)

    # Log dispatch
    log_entry = NotificationLog(
        incident_id=incident.id,
        event_type=event_type,
        dispatched_at=datetime.datetime.now(datetime.UTC),
    )
    db.add(log_entry)

    # Sync ITSM
    try:
        sync_incident(db, incident)
    except Exception as e:
        logger.exception(f"ITSM sync failed for incident {incident.id}: {e}")

    db.commit()
