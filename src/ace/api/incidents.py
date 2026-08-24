import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ace.api.deps import get_db
from ace.db.models.alerts import Alert
from ace.db.models.incidents import Incident, IncidentAlert

router = APIRouter()


@router.get("/")
def list_incidents(db: Session = Depends(get_db)) -> list[dict[str, Any]]:  # noqa: B008
    incidents = db.query(Incident).order_by(Incident.opened_at.desc()).limit(100).all()

    result = []
    for inc in incidents:
        result.append(
            {
                "id": inc.id,
                "title": inc.title,
                "status": inc.status,
                "severity": inc.severity,
                "alert_count": inc.alert_count,
                "source_tool_count": inc.source_tool_count,
                "opened_at": inc.opened_at,
                "closed_at": inc.closed_at,
                "capped": inc.capped,
                "diameter_hops": inc.diameter_hops,
            }
        )
    return result


@router.get("/{incident_id}")
def get_incident(incident_id: uuid.UUID, db: Session = Depends(get_db)) -> dict[str, Any]:  # noqa: B008
    inc = db.query(Incident).filter(Incident.id == incident_id).first()
    if not inc:
        raise HTTPException(status_code=404, detail="Incident not found")

    member_links = (
        db.query(IncidentAlert)
        .filter(IncidentAlert.incident_id == inc.id)
        .order_by(IncidentAlert.joined_at)
        .all()
    )

    alerts = []
    for link in member_links:
        alert = db.query(Alert).filter(Alert.id == link.alert_id).first()
        if alert:
            alerts.append(
                {
                    "id": alert.id,
                    "source_tool": alert.source_tool,
                    "component_id": alert.component_id,
                    "severity": alert.severity,
                    "status": alert.status,
                    "join_reason": link.join_reason,
                    "join_score": link.join_score,
                    "joined_at": link.joined_at,
                }
            )

    return {
        "id": inc.id,
        "title": inc.title,
        "status": inc.status,
        "severity": inc.severity,
        "alert_count": inc.alert_count,
        "source_tool_count": inc.source_tool_count,
        "opened_at": inc.opened_at,
        "closed_at": inc.closed_at,
        "capped": inc.capped,
        "diameter_hops": inc.diameter_hops,
        "alerts": alerts,
    }
