import uuid

from ace.correlation.containment import check_containment
from ace.correlation.decision import make_decision
from ace.correlation.signals.base import IncidentCentroid, Signal, SignalContext, SignalResult
from ace.db.models.alerts import Alert
from ace.db.models.incidents import Incident


class MockGraph:
    def __init__(self, distances: dict[tuple[uuid.UUID, uuid.UUID], int]):
        self.distances = distances

    def shortest_path_length(self, source: uuid.UUID, target: uuid.UUID) -> int:
        if source == target:
            return 0
        dist = self.distances.get((source, target)) or self.distances.get((target, source))
        if dist is not None:
            return dist
        raise Exception("No path exists")


class StubInspectionSignal(Signal):
    def __init__(self):
        self.received_centroid = None

    @property
    def name(self) -> str:
        return "same_component"

    @property
    def description(self) -> str:
        return "stub"

    def score(
        self, alert: Alert, incident: Incident, centroid: IncidentCentroid, context: SignalContext
    ) -> SignalResult:
        self.received_centroid = centroid
        return SignalResult(0.5, {"match": True})


def test_no_transitivity_via_structural_isolation():
    """
    Test: Proves that the Signal interface structurally prevents transitivity (pairwise max).
    The engine passes an IncidentCentroid (a mathematical representation of the incident)
    to the signal, rather than the list of member alerts.
    Because the signal physically lacks access to individual members, it CANNOT
    compute max(pairwise) against member alerts, thereby enforcing the NO TRANSITIVE CLOSURE
    rule structurally.
    """
    comp_a = uuid.uuid4()
    comp_b = uuid.uuid4()
    comp_c = uuid.uuid4()

    graph = MockGraph({(comp_a, comp_b): 1, (comp_b, comp_c): 1, (comp_a, comp_c): 2})

    incident = Incident(id=uuid.uuid4())
    alert_a = Alert(id=uuid.uuid4(), component_id=comp_a, environment="prod", tenant="t1")
    alert_b = Alert(id=uuid.uuid4(), component_id=comp_b, environment="prod", tenant="t1")
    alert_c = Alert(id=uuid.uuid4(), component_id=comp_c, environment="prod", tenant="t1")

    members = [alert_a, alert_b]
    candidate_incidents = [(incident, members)]

    stub_signal = StubInspectionSignal()
    context = SignalContext(db_session=None, redis_client=None, graph=graph)

    make_decision(alert_c, candidate_incidents, [stub_signal], context)

    # Assert the mechanism that prevents transitivity:
    # The signal received an IncidentCentroid, not a list of alerts.
    assert isinstance(stub_signal.received_centroid, IncidentCentroid)

    # Assert that the centroid only contains the mathematical component set {A, B}
    assert stub_signal.received_centroid.component_ids == {comp_a, comp_b}

    # The signal physically cannot access alert_a or alert_b, so max(pairwise)
    # over alert IDs or alert texts is impossible.


def test_hard_partitions():
    comp_a = uuid.uuid4()
    graph = MockGraph({})

    incident = Incident(id=uuid.uuid4())
    alert_a = Alert(id=uuid.uuid4(), component_id=comp_a, environment="prod", tenant="t1")
    alert_b = Alert(id=uuid.uuid4(), component_id=comp_a, environment="staging", tenant="t1")

    members = [alert_a]

    containment = check_containment(alert_b, incident, members, graph)
    assert containment.allowed is False
    assert "Environment mismatch" in containment.reason


def test_empty_centroid_refusal():
    graph = MockGraph({})
    incident = Incident(id=uuid.uuid4())

    # Incident member has NO component (empty centroid)
    alert_a = Alert(id=uuid.uuid4(), environment="prod", tenant="t1")
    # Incoming alert HAS a component
    alert_b = Alert(id=uuid.uuid4(), component_id=uuid.uuid4(), environment="prod", tenant="t1")

    containment = check_containment(alert_b, incident, [alert_a], graph)

    assert containment.allowed is False
    assert "Empty Centroid" in containment.reason
