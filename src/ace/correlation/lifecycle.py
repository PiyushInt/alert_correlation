import datetime
import logging
import uuid
from collections import Counter
from typing import Any

from sqlalchemy.orm import Session

from ace.db.models.alerts import Alert
from ace.db.models.incidents import Incident, IncidentAlert, IncidentSplit, SplitSuppression
from ace.metrics import registry
from ace.notification.dispatcher import dispatch_incident_event

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
    db: Session,
    alert: Alert,
    incident: Incident,
    members: list[Alert],
    score: float,
    reason: str,
    signal_scores: dict[str, float] | None = None,
) -> None:
    """Adds an alert to an existing incident."""
    now = datetime.datetime.now(datetime.UTC)

    incident_alert = IncidentAlert(
        incident_id=incident.id,
        alert_id=alert.id,
        join_reason=reason,
        join_score=score,
        signal_scores=signal_scores,
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

    all_resolved = True
    for a in members:
        if a.status == "resolved":
            continue
        # Check if a resolve alert exists for this firing member
        resolve_exists = db.query(Alert).filter(Alert.resolves_alert_id == a.id).first()
        if not resolve_exists:
            all_resolved = False
            break

    if all_resolved or window_expired:
        incident.status = "resolved"
        incident.closed_at = datetime.datetime.now(datetime.UTC)
        logger.info(
            f"Incident {incident.id} auto-resolved. "
            f"all_resolved={all_resolved}, window_expired={window_expired}"
        )
        return True

    return False


def split_incident(
    db: Session, r: Any, incident: Incident, partitions: list[list[str]], operator: str, reason: str
) -> list[Incident]:
    now = datetime.datetime.now(datetime.UTC)
    incident.status = "split"
    incident.closed_at = now

    new_incidents = []
    partition_fingerprints = []

    for partition in partitions:
        alert_ids = [uuid.UUID(a_id) for a_id in partition]
        members = db.query(Alert).filter(Alert.id.in_(alert_ids)).all()
        if not members:
            continue

        initial_alert = members[0]
        new_inc = Incident(
            title=generate_title(members),
            status="open",
            severity=initial_alert.severity,
            opened_at=now,
            alert_count=len(members),
            source_tool_count=len({a.source_tool for a in members}),
            diameter_hops=0,
            capped=False,
            split_from_incident_id=incident.id,
        )
        db.add(new_inc)
        db.flush()
        new_incidents.append(new_inc)

        fingerprints = {a.fingerprint for a in members}
        partition_fingerprints.append((new_inc.id, fingerprints))

        for alert in members:
            # We don't update alert.incident_id to preserve the ledger
            incident_alert = IncidentAlert(
                incident_id=new_inc.id,
                alert_id=alert.id,
                join_reason="Split partition",
                join_score=1.0,
                joined_at=now,
            )
            db.add(incident_alert)

        from ace.correlation.window import add_open_incident

        add_open_incident(r, new_inc.id)

    # Enforce anti-affinity between partitions
    for i, (inc_id_a, _fps_a) in enumerate(partition_fingerprints):
        for j, (_inc_id_b, fps_b) in enumerate(partition_fingerprints):
            if i == j:
                continue
            for fp in fps_b:
                suppression = SplitSuppression(
                    incident_id=inc_id_a, alert_fingerprint=fp, created_at=now
                )
                db.add(suppression)

    split_record = IncidentSplit(
        original_incident_id=incident.id,
        resulting_incident_ids=[str(inc.id) for inc in new_incidents],
        reason=reason,
        operator=operator,
        created_at=now,
    )
    db.add(split_record)
    db.flush()

    # Recompute root cause for new incidents
    from ace.ranking.ranker import rank_root_cause_candidates

    for inc in new_incidents:
        rank_root_cause_candidates(db, inc, now)
        dispatch_incident_event(db, inc, "split")

    return new_incidents


def merge_incidents(db: Session, r: Any, incident_a: Incident, incident_b: Incident) -> None:
    now = datetime.datetime.now(datetime.UTC)

    # Check for anti-affinity
    members_a = db.query(IncidentAlert).filter(IncidentAlert.incident_id == incident_a.id).all()
    members_b = db.query(IncidentAlert).filter(IncidentAlert.incident_id == incident_b.id).all()

    # Since suppressions are keyed on (incident_id, fingerprint), we must check if incident_a
    # has a suppression against any fingerprint in incident_b, or vice versa.
    b_alert_ids = [m.alert_id for m in members_b]
    b_alerts = db.query(Alert).filter(Alert.id.in_(b_alert_ids)).all()
    b_fps = {a.fingerprint for a in b_alerts}

    suppressions_a = (
        db.query(SplitSuppression).filter(SplitSuppression.incident_id == incident_a.id).all()
    )
    for s in suppressions_a:
        if s.alert_fingerprint in b_fps:
            raise ValueError(
                f"Merge refused: Incident {incident_a.id} has anti-affinity "
                f"with fingerprint {s.alert_fingerprint}"
            )

    a_alert_ids = [m.alert_id for m in members_a]
    a_alerts = db.query(Alert).filter(Alert.id.in_(a_alert_ids)).all()
    a_fps = {a.fingerprint for a in a_alerts}

    suppressions_b = (
        db.query(SplitSuppression).filter(SplitSuppression.incident_id == incident_b.id).all()
    )
    for s in suppressions_b:
        if s.alert_fingerprint in a_fps:
            raise ValueError(
                f"Merge refused: Incident {incident_b.id} has anti-affinity "
                f"with fingerprint {s.alert_fingerprint}"
            )

    # Proceed with merge
    incident_b.status = "merged"
    incident_b.closed_at = now

    for alert in b_alerts:
        incident_alert = IncidentAlert(
            incident_id=incident_a.id,
            alert_id=alert.id,
            join_reason="Manual operator merge",
            join_score=1.0,
            joined_at=now,
        )
        db.add(incident_alert)
        a_alerts.append(alert)

    incident_a.alert_count = len(a_alerts)
    incident_a.source_tool_count = len({a.source_tool for a in a_alerts})
    incident_a.title = generate_title(a_alerts)

    from ace.correlation.window import remove_open_incident

    remove_open_incident(r, incident_b.id)

    from ace.ranking.ranker import rank_root_cause_candidates

    rank_root_cause_candidates(db, incident_a, now)
    dispatch_incident_event(db, incident_a, "escalation")
