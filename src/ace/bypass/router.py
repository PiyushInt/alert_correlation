import json
import logging
from pathlib import Path

from ace.bypass.health import State
from ace.ingestion.models import NormalisedAlert
from ace.queue.streams import publish_to_stream

logger = logging.getLogger(__name__)

NOTIFICATIONS_DIR = Path("notifications")


def _notify(alert: NormalisedAlert, degraded: bool) -> None:
    """
    Writes the alert to the notifications directory.
    If degraded=True, adds a banner indicating the bypass path.
    """
    NOTIFICATIONS_DIR.mkdir(exist_ok=True)

    payload = alert.model_dump(mode="json")
    if degraded:
        payload["_banner"] = "[DEGRADED] Alert routed via bypass path. Correlation unavailable."

    filename = NOTIFICATIONS_DIR / f"{alert.external_id}_{alert.starts_at.timestamp()}.json"
    try:
        with open(filename, "w") as f:
            json.dump(payload, f, indent=2)
    except OSError as e:
        logger.error(f"Failed to write notification to {filename}: {e}")


def route_alert(alert: NormalisedAlert, current_state: State) -> None:
    """
    Routes an alert based on the current system state and alert severity.
    """
    is_critical = alert.severity == "critical"

    if current_state == "BYPASS":
        # BYPASS: pipeline unavailable. RAW to notification, NO publish.
        _notify(alert, degraded=True)
    elif is_critical:
        # CRITICAL in OK state: Notify immediately (no banner) AND publish.
        _notify(alert, degraded=False)
        if alert.id:
            success = publish_to_stream(alert.id)
            if not success:
                logger.warning(f"Publish failed for critical alert {alert.id} during OK state.")
    else:
        # Normal alert in OK state: Publish only.
        success = False
        if alert.id:
            success = publish_to_stream(alert.id)
        if not success:
            # Publish failure acts as a local BYPASS for this alert.
            logger.warning(
                f"Publish failed for normal alert {alert.id}. Failing open to notifications."
            )
            _notify(alert, degraded=True)
