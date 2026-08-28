import datetime
import uuid

from sqlalchemy.orm import Session

from ace.db.models.incidents import Incident, ItsmRecord, NotificationLog
from ace.notification.dispatcher import dispatch_incident_event


def test_dispatcher_and_itsm_idempotency(db_session: Session):
    incident = Incident(
        id=uuid.uuid4(),
        title="Test Incident",
        status="open",
        severity="high",
        opened_at=datetime.datetime.now(datetime.UTC),
        alert_count=1,
        source_tool_count=1,
        diameter_hops=0,
        capped=False,
    )
    db_session.add(incident)
    db_session.flush()

    # Dispatch once
    dispatch_incident_event(db_session, incident, "open")

    logs = (
        db_session.query(NotificationLog).filter(NotificationLog.incident_id == incident.id).all()
    )
    assert len(logs) == 1

    itsm = db_session.query(ItsmRecord).filter(ItsmRecord.incident_id == incident.id).all()
    assert len(itsm) == 1

    # Dispatch again (idempotent)
    dispatch_incident_event(db_session, incident, "open")

    logs_after = (
        db_session.query(NotificationLog).filter(NotificationLog.incident_id == incident.id).all()
    )
    assert len(logs_after) == 1

    itsm_after = db_session.query(ItsmRecord).filter(ItsmRecord.incident_id == incident.id).all()
    assert len(itsm_after) == 1
