from ace.correlation.signals.base import IncidentCentroid, SignalContext
from ace.correlation.signals.cooccurrence import CooccurrenceSignal, get_alert_type
from ace.db.models.alerts import Alert
from ace.db.models.incidents import Incident


def test_cooccurrence_empty_stats():
    signal = CooccurrenceSignal()
    alert = Alert(labels={"alertname": "HighCPU"}, annotations={}, external_id="")

    # centroid with alert_types but NO stats in context
    centroid = IncidentCentroid(alert_types={"HighMemory"}, cooccurrence_stats={})
    context = SignalContext(None, None, None)

    result = signal.score(alert, Incident(), centroid, context)
    assert result.score == 0.0
    assert result.evidence["match"] is False


def test_cooccurrence_no_overlap():
    signal = CooccurrenceSignal()
    alert = Alert(labels={"alertname": "HighCPU"}, annotations={}, external_id="")

    centroid = IncidentCentroid(
        alert_types={"DiskFull"},
        cooccurrence_stats={
            "HighCPU|HighMemory": {"co_occurrence_count": 10, "confirmed_count": 8}
        },
    )
    context = SignalContext(None, None, None)

    result = signal.score(alert, Incident(), centroid, context)
    assert result.score == 0.0
    assert result.evidence["match"] is False


def test_cooccurrence_match():
    signal = CooccurrenceSignal()
    alert = Alert(labels={"alertname": "HighCPU"}, annotations={}, external_id="")

    centroid = IncidentCentroid(
        alert_types={"DiskFull", "HighMemory"},
        cooccurrence_stats={
            # Incoming alert is HighCPU. It matches HighMemory in the centroid.
            "HighCPU|HighMemory": {"co_occurrence_count": 10, "confirmed_count": 8}
        },
    )
    context = SignalContext(None, None, None)

    result = signal.score(alert, Incident(), centroid, context)
    assert result.score == 0.8  # 8 / 10
    assert result.evidence["match"] is True
    assert result.evidence["matched_type"] == "HighMemory"


def test_get_alert_type():
    a1 = Alert(labels={"alertname": "Foo"}, annotations={}, external_id="bar")
    assert get_alert_type(a1) == "Foo"

    a2 = Alert(labels={"name": "Baz"}, annotations={}, external_id="bar")
    assert get_alert_type(a2) == "Baz"

    a3 = Alert(labels={}, annotations={}, external_id="Ext123")
    assert get_alert_type(a3) == "Ext123"
