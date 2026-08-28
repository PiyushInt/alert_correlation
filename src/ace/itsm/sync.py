import datetime

from sqlalchemy.orm import Session

from ace.db.models.incidents import Incident, ItsmRecord
from ace.itsm.adapters.json_file import JsonFileAdapter


def sync_incident(db: Session, incident: Incident) -> None:
    adapter = JsonFileAdapter()

    data = {
        "title": incident.title,
        "status": incident.status,
        "severity": incident.severity,
        "opened_at": incident.opened_at.isoformat() if incident.opened_at else None,
        "closed_at": incident.closed_at.isoformat() if incident.closed_at else None,
        "alert_count": incident.alert_count,
    }

    record = db.query(ItsmRecord).filter(ItsmRecord.incident_id == incident.id).first()
    now = datetime.datetime.now(datetime.UTC)

    if record:
        adapter.update(record.external_id, data)
        record.updated_at = now
    else:
        ext_id = adapter.create(str(incident.id), data)
        new_record = ItsmRecord(
            incident_id=incident.id, external_id=ext_id, created_at=now, updated_at=now
        )
        db.add(new_record)
