from sqlalchemy.orm import Session

from ace.db.models.alerts import Alert
from ace.db.models.incidents import Incident, IncidentAlert, RootCauseCandidate


def render_notification(db: Session, incident: Incident, event_type: str) -> str:
    # member alerts
    members = db.query(IncidentAlert).filter(IncidentAlert.incident_id == incident.id).all()
    alert_ids = [m.alert_id for m in members]
    alerts = db.query(Alert).filter(Alert.id.in_(alert_ids)).all()

    bypassed = any(a.bypassed for a in alerts)
    banner = "BYPASS" if bypassed else "DEGRADED"

    out = [f"=== INCIDENT NOTIFICATION [{event_type.upper()}] ==="]
    out.append(f"Incident: {incident.id}")
    out.append(f"Title: {incident.title}")
    out.append(f"Severity: {incident.severity}")
    out.append(f"State Banner: {banner}")
    out.append("")
    out.append("MEMBER ALERTS:")
    for a in alerts:
        out.append(f" - {a.source_tool}: {a.id} ({a.fingerprint})")

    out.append("")
    out.append("ROOT CAUSE CANDIDATES (Top 3):")
    candidates = (
        db.query(RootCauseCandidate)
        .filter(RootCauseCandidate.incident_id == incident.id)
        .order_by(RootCauseCandidate.rank.asc())
        .limit(3)
        .all()
    )
    if not candidates:
        out.append(" No candidates available.")
    else:
        for c in candidates:
            uncertain = "(UNCERTAIN)" if c.uncertain else ""
            out.append(f" {c.rank}. Component {c.component_id} Score: {c.score:.2f} {uncertain}")
            out.append(f"    Evidence: {c.evidence}")

    out.append("")
    out.append("FEEDBACK API:")
    out.append(f" POST /incidents/{incident.id}/feedback")
    out.append(' {"verdict": "correct|wrong_group|missed_member|wrong_cause", "operator": "you"}')

    return "\n".join(out)
