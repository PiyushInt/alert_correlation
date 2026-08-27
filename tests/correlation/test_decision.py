import uuid

import pytest

from ace.config import settings
from ace.correlation.decision import make_decision
from ace.correlation.signals.base import IncidentCentroid, Signal, SignalContext, SignalResult
from ace.db.models.alerts import Alert
from ace.db.models.incidents import Incident


class MockSignal(Signal):
    def __init__(self, name: str, fixed_score: float):
        self._name = name
        self.fixed_score = fixed_score

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "Mock signal"

    def score(
        self,
        alert: Alert,
        incident: Incident,
        centroid: IncidentCentroid,
        context: SignalContext,
    ) -> SignalResult:
        return SignalResult(score=self.fixed_score, evidence={})


@pytest.fixture
def weights():
    """Pin weights for these tests and restore afterwards."""
    saved = {
        k: getattr(settings, k)
        for k in (
            "SIGNAL_WEIGHT_SAME_COMPONENT",
            "SIGNAL_WEIGHT_DEPENDENCY_PROXIMITY",
            "SIGNAL_WEIGHT_TEXT_SIMILARITY",
            "SIGNAL_WEIGHT_COOCCURRENCE",
            "CORRELATION_THRESHOLD",
        )
    }
    settings.SIGNAL_WEIGHT_SAME_COMPONENT = 1.0
    settings.SIGNAL_WEIGHT_DEPENDENCY_PROXIMITY = 0.6
    settings.SIGNAL_WEIGHT_TEXT_SIMILARITY = 0.5
    settings.SIGNAL_WEIGHT_COOCCURRENCE = 0.5
    settings.CORRELATION_THRESHOLD = 1.0
    yield
    for k, v in saved.items():
        setattr(settings, k, v)


@pytest.fixture
def candidate():
    alert = Alert(id=uuid.uuid4(), environment="prod")
    member = Alert(id=uuid.uuid4(), environment="prod")
    incident = Incident(id=uuid.uuid4())
    context = SignalContext(db_session=None, redis_client=None, graph=None, alert_type_stats={})
    return alert, [(incident, [member])], context


def test_same_component_alone_merges(weights, candidate):
    alert, candidates, context = candidate
    d = make_decision(alert, candidates, [MockSignal("same_component", 1.0)], context)
    assert d.incident is not None


def test_dependency_proximity_alone_does_not_merge(weights, candidate):
    alert, candidates, context = candidate
    d = make_decision(alert, candidates, [MockSignal("dependency_proximity", 1.0)], context)
    assert d.incident is None


def test_text_similarity_alone_does_not_merge(weights, candidate):
    alert, candidates, context = candidate
    d = make_decision(alert, candidates, [MockSignal("text_similarity", 0.525)], context)
    assert d.incident is None


def test_two_circumstantial_signals_merge(weights, candidate):
    alert, candidates, context = candidate
    signals = [MockSignal("dependency_proximity", 1.0), MockSignal("text_similarity", 0.8)]
    d = make_decision(alert, candidates, signals, context)
    assert d.incident is not None
