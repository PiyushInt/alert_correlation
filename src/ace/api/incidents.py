import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ace.api.deps import get_db
from ace.correlation.lifecycle import merge_incidents, split_incident
from ace.db.models.alerts import Alert
from ace.db.models.incidents import Incident, IncidentAlert, IncidentFeedback, IncidentSplit

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


class SplitRequest(BaseModel):
    partitions: list[list[str]]
    operator: str
    reason: str


@router.post("/{incident_id}/split")
def api_split_incident(
    incident_id: str,
    data: SplitRequest,
    db: Session = Depends(get_db),  # noqa: B008
) -> dict[str, Any]:
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    from ace.queue.streams import get_redis_client

    r = get_redis_client()

    new_incs = split_incident(db, r, incident, data.partitions, data.operator, data.reason)
    db.commit()
    return {"status": "ok", "new_incident_ids": [str(i.id) for i in new_incs]}


@router.post("/{incident_a_id}/merge/{incident_b_id}")
def api_merge_incidents(
    incident_a_id: str,
    incident_b_id: str,
    db: Session = Depends(get_db),  # noqa: B008
) -> dict[str, Any]:
    inc_a = db.query(Incident).filter(Incident.id == incident_a_id).first()
    inc_b = db.query(Incident).filter(Incident.id == incident_b_id).first()
    if not inc_a or not inc_b:
        raise HTTPException(status_code=404, detail="Incident not found")

    from ace.queue.streams import get_redis_client

    r = get_redis_client()

    try:
        merge_incidents(db, r, inc_a, inc_b)
        db.commit()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"status": "ok"}


@router.get("/{incident_id}/history")
def get_incident_history(
    incident_id: str,
    db: Session = Depends(get_db),  # noqa: B008
) -> list[dict[str, Any]]:
    splits = db.query(IncidentSplit).filter(IncidentSplit.original_incident_id == incident_id).all()
    feedbacks = db.query(IncidentFeedback).filter(IncidentFeedback.incident_id == incident_id).all()

    history = []
    for s in splits:
        history.append(
            {"type": "split", "created_at": s.created_at.isoformat(), "reason": s.reason}
        )
    for f in feedbacks:
        history.append(
            {"type": "feedback", "created_at": f.created_at.isoformat(), "verdict": f.verdict}
        )

    history.sort(key=lambda x: x["created_at"])
    return history
