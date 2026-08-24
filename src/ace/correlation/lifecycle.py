import datetime
import logging
from collections import Counter

from sqlalchemy.orm import Session

from ace.db.models.alerts import Alert
from ace.db.models.incidents import Incident, IncidentAlert
from ace.metrics import registry

logger = logging.getLogger(__name__)


def generate_title(members: list[Alert]) -> str:
    """Generates a title based on the components in the incident."""
    if not members:
        return "Empty Incident"

    comp_names = []
    for a in members:
        # In a real system, we'd look up the component canonical name.
        # For speed, we just use the ID or a fallback.
        if a.component_id:
            comp_names.append(str(a.component_id)[:8])
        else:
            comp_names.append("unknown")

    c = Counter(comp_names)
    most_common = c.most_common(2)
    names = ", ".join([name for name, _ in most_common])
    return f"Incident affecting {names}"


def open_incident(db: Session, initial_alert: Alert) -> Incident:
    """Creates a new incident seeded by the initial alert."""
    now = datetime.datetime.now(datetime.UTC)

    incident = Incident(
        title=f"Incident affecting {str(initial_alert.component_id)[:8] if initial_alert.component_id else 'unknown'}",  # noqa: E501
        status="open",
        severity=initial_alert.severity,
        opened_at=now,
        alert_count=1,
        source_tool_count=1,
        diameter_hops=0,
        capped=False,
    )
    db.add(incident)
    db.flush()

    # Link alert
    incident_alert = IncidentAlert(
        incident_id=incident.id,
        alert_id=initial_alert.id,
        join_reason="Initial alert",
        join_score=1.0,
        joined_at=now,
    )
    db.add(incident_alert)

    initial_alert.incident_id = incident.id

    registry.inc_counter("ace_incidents_created_total")
    return incident


def accrete_alert(
    db: Session, alert: Alert, incident: Incident, members: list[Alert], score: float, reason: str
) -> None:
    """Adds an alert to an existing incident."""
    now = datetime.datetime.now(datetime.UTC)

    incident_alert = IncidentAlert(
        incident_id=incident.id,
        alert_id=alert.id,
        join_reason=reason,
        join_score=score,
        joined_at=now,
    )
    db.add(incident_alert)

    alert.incident_id = incident.id

    # Update aggregates
    members.append(alert)
    incident.alert_count = len(members)

    source_tools = {a.source_tool for a in members}
    incident.source_tool_count = len(source_tools)

    incident.title = generate_title(members)

    registry.inc_counter("ace_incident_alerts_merged_total")


def auto_resolve_if_ready(
    db: Session, incident: Incident, members: list[Alert], window_expired: bool = False
) -> bool:  # noqa: E501
    """
    Checks if an incident should be auto-resolved.
    Returns True if resolved.
    """
    if incident.status == "resolved":
        return True

    all_resolved = all(a.status == "resolved" for a in members)

    if all_resolved or window_expired:
        incident.status = "resolved"
        incident.closed_at = datetime.datetime.now(datetime.UTC)
        logger.info(
            f"Incident {incident.id} auto-resolved. "
            f"all_resolved={all_resolved}, window_expired={window_expired}"
        )
        return True

    return False
