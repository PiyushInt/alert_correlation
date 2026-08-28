import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ace.api.deps import get_db
from ace.db.models.incidents import IncidentFeedback

router = APIRouter(prefix="/incidents", tags=["feedback"])


class FeedbackCreate(BaseModel):
    verdict: str
    operator: str
    note: str
    alert_id: str | None = None


@router.post("/{incident_id}/feedback")
def submit_feedback(
    incident_id: str,
    data: FeedbackCreate,
    db: Session = Depends(get_db),  # noqa: B008
) -> dict[str, Any]:
    feedback = IncidentFeedback(
        incident_id=uuid.UUID(incident_id),
        alert_id=uuid.UUID(data.alert_id) if data.alert_id else None,
        verdict=data.verdict,
        operator=data.operator,
        note=data.note,
        created_at=datetime.utcnow(),
    )
    db.add(feedback)
    from ace.metrics import registry

    registry.inc_counter("ace_incident_feedback_total", {"verdict": data.verdict})

    if data.verdict == "wrong_group" and data.alert_id:
        from ace.db.models.incidents import IncidentAlert

        ia = (
            db.query(IncidentAlert)
            .filter(
                IncidentAlert.incident_id == uuid.UUID(incident_id),
                IncidentAlert.alert_id == uuid.UUID(data.alert_id),
            )
            .first()
        )
        if ia and ia.signal_scores:
            best_sig = max(ia.signal_scores.items(), key=lambda x: x[1])[0]
            registry.inc_counter("ace_signal_disagreement_total", {"signal_name": best_sig})

    db.commit()
    return {"status": "ok"}
