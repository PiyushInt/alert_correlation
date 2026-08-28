import datetime
import logging
import uuid

import redis
from sqlalchemy.orm import Session

from ace.config import settings
from ace.correlation.decision import make_decision
from ace.correlation.lifecycle import accrete_alert, auto_resolve_if_ready, open_incident
from ace.correlation.signals.base import SignalContext
from ace.correlation.signals.cooccurrence import get_alert_type
from ace.correlation.signals.registry import get_active_signals
from ace.correlation.window import add_open_incident, get_open_incidents, remove_open_incident
from ace.db.models.alerts import Alert, AlertTypeStat
from ace.db.models.incidents import Incident, IncidentAlert
from ace.dependency.graph import graph_instance
from ace.metrics import registry

logger = logging.getLogger(__name__)


def process_alert_correlation(db: Session, r: redis.Redis, alert: Alert) -> None:
    """
    Main entry point for Pipeline Stage 4: Correlation Engine.
    Orchestrates candidate gathering, decision making, and lifecycle execution.
    """
    if alert.incident_id:
        # Already correlated (maybe re-queued)
        return

    if alert.resolves_alert_id:
        logger.info(f"Alert {alert.id} is a resolution. Triggering lifecycle check.")
        original_alert = db.query(Alert).filter(Alert.id == alert.resolves_alert_id).first()
        if original_alert and original_alert.incident_id:
            incident = db.query(Incident).filter(Incident.id == original_alert.incident_id).first()
            if incident:
                member_links = (
                    db.query(IncidentAlert).filter(IncidentAlert.incident_id == incident.id).all()
                )
                member_ids = [link.alert_id for link in member_links]
                members = db.query(Alert).filter(Alert.id.in_(member_ids)).all()
                if auto_resolve_if_ready(db, incident, members, window_expired=False):
                    remove_open_incident(r, incident.id)
                db.commit()
        return

    # Critical severity bypass: notify immediately and ALSO correlate
    is_critical_bypass = alert.severity.lower() == settings.CRITICAL_BYPASS_SEVERITY.lower()
    if is_critical_bypass:
        logger.info(f"Alert {alert.id} is CRITICAL. Triggering immediate notification bypass.")
        # In a real system, we'd trigger the notification webhook here immediately.

    # 1. Fetch Candidate Incidents from Window
    open_incident_ids = get_open_incidents(r)

    candidate_incidents: list[tuple[Incident, list[Alert]]] = []
    expired_incidents: list[uuid.UUID] = []

    for inc_id in open_incident_ids:
        incident = db.query(Incident).filter(Incident.id == inc_id).first()
        if not incident:
            remove_open_incident(r, inc_id)
            continue

        # Get all members
        member_links = db.query(IncidentAlert).filter(IncidentAlert.incident_id == inc_id).all()
        member_ids = [link.alert_id for link in member_links]
        members = db.query(Alert).filter(Alert.id.in_(member_ids)).all()

        # Check if window expired for this incident relative to the alert's starts_at
        # Assuming the incident window starts at incident.opened_at
        age = (alert.starts_at - incident.opened_at).total_seconds()

        if age > settings.CORRELATION_WINDOW:
            expired_incidents.append(inc_id)
            auto_resolve_if_ready(db, incident, members, window_expired=True)
            db.commit()
            continue

        # Also auto-resolve if all members are resolved
        if auto_resolve_if_ready(db, incident, members, window_expired=False):
            expired_incidents.append(inc_id)
            db.commit()
            continue

        candidate_incidents.append((incident, members))

    for inc_id in expired_incidents:
        remove_open_incident(r, inc_id)

    # 2. Make Decision (PURE)
    alert_type = get_alert_type(alert)
    # Query stats for this alert type against any other type
    stats_rows = (
        db.query(AlertTypeStat)
        .filter(
            (AlertTypeStat.alert_type_a == alert_type) | (AlertTypeStat.alert_type_b == alert_type)
        )
        .all()
    )

    alert_type_stats = {}
    for row in stats_rows:
        key = f"{row.alert_type_a}|{row.alert_type_b}"
        alert_type_stats[key] = {
            "co_occurrence_count": row.co_occurrence_count,
            "confirmed_count": row.confirmed_count,
        }

    context = SignalContext(
        db_session=db, redis_client=r, graph=graph_instance, alert_type_stats=alert_type_stats
    )
    signals = get_active_signals()

    decision = make_decision(alert, candidate_incidents, signals, context)

    # Log all containments that were refused
    for refusal in decision.refusals:
        logger.warning(
            f"CONTAINMENT REFUSED: Alert {alert.id} refused by Incident {refusal['incident_id']}. "
            f"Reason: {refusal['reason']}",
            extra={
                "extra_data": {
                    "alert_id": str(alert.id),
                    "incident_id": refusal["incident_id"],
                    "reason": refusal["reason"],
                }
            },
        )

    # Log all evaluated candidate signals (allowed containments)
    for eval_result in decision.evaluations:
        logger.info(
            f"EVALUATION: Alert {alert.id} evaluated against "
            f"Incident {eval_result['incident_id']}. "
            f"Total Score: {eval_result['total']:.2f}",
            extra={
                "extra_data": {
                    "alert_id": str(alert.id),
                    "incident_id": eval_result["incident_id"],
                    "scores": eval_result["scores"],
                    "weighted_scores": eval_result.get("weighted_scores", {}),
                    "total": eval_result["total"],
                }
            },
        )

    # 3. Execute Decision
    if decision.incident:
        logger.info(
            f"Alert {alert.id} joined Incident {decision.incident.id}. Reason: {decision.reason}"
        )

        # Find the members list for the chosen incident
        members = next(m for i, m in candidate_incidents if i.id == decision.incident.id)

        accrete_alert(
            db,
            alert,
            decision.incident,
            members,
            decision.score,
            decision.reason,
            decision.signal_scores,
        )
        # Update window
        add_open_incident(r, decision.incident.id)

    else:
        if len(candidate_incidents) == 0:
            logger.info(
                f"Alert {alert.id} opened a new Incident. Reason: No candidates were retrieved "
                f"from the window."
            )
        else:
            inc_ids = [str(inc.id) for inc, _ in candidate_incidents]
            logger.info(
                f"Alert {alert.id} opened a new Incident. Reason: Candidates existed and every "
                f"one was refused (evaluated {len(candidate_incidents)} candidates: {inc_ids})."
            )

        incident = open_incident(db, alert)
        add_open_incident(r, incident.id)

        # Track Added-Latency for a NEW incident: Receipt to first notification.
        # This is (now - alert.received_at)
        now = datetime.datetime.now(datetime.UTC)
        latency = (now - alert.received_at).total_seconds()
        registry.observe_histogram("ace_incident_notification_latency_seconds", latency)

    db.commit()

    # Pipeline Stage 5: Rank Root Cause
    target_incident = decision.incident if decision.incident else incident
    try:
        from ace.ranking.ranker import rank_root_cause_candidates
        rank_root_cause_candidates(db, target_incident, datetime.datetime.now(datetime.UTC))
    except Exception as e:
        # Should be handled in rank_root_cause_candidates, but just in case
        logger.exception(f"Unexpected error calling ranker for incident {target_incident.id}: {e}")
