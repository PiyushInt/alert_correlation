import uuid

from ace.correlation.signals.base import IncidentCentroid, SignalContext
from ace.correlation.signals.same_component import SameComponentSignal
from ace.db.models.alerts import Alert
from ace.db.models.incidents import Incident


def test_null_components_score_zero():
    """
    Proves that two alerts with component_id=None score 0.0 for same_component.
    NULL != NULL in correlation logic.
    """
    alert_b = Alert(id=uuid.uuid4(), component_id=None)

    incident = Incident(id=uuid.uuid4())
    centroid = IncidentCentroid(component_ids=set())

    signal = SameComponentSignal()
    # Mock context
    context = SignalContext(db_session=None, redis_client=None, graph=None)

    result = signal.score(alert_b, incident, centroid, context)

    assert result.score == 0.0
    assert result.evidence["match"] is False
    assert result.evidence["reason"] == "alert component is null"


def test_same_component_matches_centroid():
    comp_a = uuid.uuid4()
    alert_b = Alert(id=uuid.uuid4(), component_id=comp_a)

    incident = Incident(id=uuid.uuid4())
    centroid = IncidentCentroid(component_ids={comp_a})

    signal = SameComponentSignal()
    context = SignalContext(db_session=None, redis_client=None, graph=None)

    result = signal.score(alert_b, incident, centroid, context)

    assert result.score == 1.0
    assert result.evidence["match"] is True
