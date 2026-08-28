import datetime
import uuid

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from ace.db.models.incidents import Incident, IncidentFeedback
from ace.main import app


def test_feedback_submission(db_session: Session):
    from ace.api.deps import get_db

    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)

    incident = Incident(
        id=uuid.uuid4(),
        title="Test Feedback Incident",
        status="open",
        severity="high",
        opened_at=datetime.datetime.now(datetime.UTC),
        alert_count=1,
        source_tool_count=1,
        diameter_hops=0,
        capped=False,
    )
    db_session.add(incident)
    db_session.commit()

    payload = {"verdict": "correct", "operator": "test_operator", "note": "Looks good"}

    response = client.post(f"/incidents/{str(incident.id)}/feedback", json=payload)
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    # Verify DB
    fb = (
        db_session.query(IncidentFeedback)
        .filter(IncidentFeedback.incident_id == incident.id)
        .first()
    )
    assert fb is not None
    assert fb.verdict == "correct"
    assert fb.operator == "test_operator"
