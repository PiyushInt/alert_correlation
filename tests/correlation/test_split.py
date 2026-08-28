import datetime
import uuid

import pytest
from sqlalchemy.orm import Session

from ace.correlation.lifecycle import merge_incidents, split_incident
from ace.db.models.alerts import Alert
from ace.db.models.incidents import Incident, IncidentAlert, SplitSuppression


class MockRedis:
    def sadd(self, *args, **kwargs):
        pass

    def srem(self, *args, **kwargs):
        pass

    def zadd(self, *args, **kwargs):
        pass

    def zrem(self, *args, **kwargs):
        pass


def test_split_incident_and_anti_affinity(db_session: Session):
    # Setup initial incident
    incident = Incident(
        title="Test Incident",
        status="open",
        severity="high",
        opened_at=datetime.datetime.now(datetime.UTC),
        alert_count=2,
        source_tool_count=2,
        diameter_hops=0,
        capped=False,
    )
    db_session.add(incident)
    db_session.flush()

    alert1 = Alert(
        id=uuid.uuid4(),
        fingerprint="fp1",
        external_id="test1",
        environment="prod",
        tenant="t1",
        starts_at=datetime.datetime.now(datetime.UTC),
        source_tool="prometheus",
        status="firing",
        severity="high",
        component_unresolved=True,
        received_at=datetime.datetime.now(datetime.UTC),
    )
    alert2 = Alert(
        id=uuid.uuid4(),
        fingerprint="fp2",
        external_id="test2",
        environment="prod",
        tenant="t1",
        starts_at=datetime.datetime.now(datetime.UTC),
        source_tool="zabbix",
        status="firing",
        severity="high",
        component_unresolved=True,
        received_at=datetime.datetime.now(datetime.UTC),
    )
    db_session.add_all([alert1, alert2])
    db_session.flush()

    db_session.add_all(
        [
            IncidentAlert(
                incident_id=incident.id,
                alert_id=alert1.id,
                join_reason="test",
                join_score=1.0,
                joined_at=datetime.datetime.now(datetime.UTC),
            ),
            IncidentAlert(
                incident_id=incident.id,
                alert_id=alert2.id,
                join_reason="test",
                join_score=1.0,
                joined_at=datetime.datetime.now(datetime.UTC),
            ),
        ]
    )
    db_session.flush()

    r = MockRedis()

    # Execute split
    new_incs = split_incident(
        db_session, r, incident, [[str(alert1.id)], [str(alert2.id)]], "op", "reason"
    )
    db_session.flush()

    assert len(new_incs) == 2
    assert incident.status == "split"

    inc1, inc2 = new_incs

    # Verify suppression
    suppressions = db_session.query(SplitSuppression).all()
    assert len(suppressions) == 2

    s1 = db_session.query(SplitSuppression).filter(SplitSuppression.incident_id == inc1.id).first()
    s2 = db_session.query(SplitSuppression).filter(SplitSuppression.incident_id == inc2.id).first()

    assert s1.alert_fingerprint == "fp2"
    assert s2.alert_fingerprint == "fp1"

    # Test merge refusal
    with pytest.raises(ValueError, match="Merge refused"):
        merge_incidents(db_session, r, inc1, inc2)
