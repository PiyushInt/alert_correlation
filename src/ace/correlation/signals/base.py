import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from ace.db.models.alerts import Alert
from ace.db.models.incidents import Incident


@dataclass
class IncidentCentroid:
    """
    Represents the mathematical centroid of an incident.
    Signals must score against this centroid, NOT against individual members.
    """

    component_ids: set[uuid.UUID] = field(default_factory=set)
    normalised_text: set[str] = field(default_factory=set)
    alert_types: set[str] = field(default_factory=set)
    cooccurrence_stats: dict[str, dict[str, int]] = field(default_factory=dict)


class SignalResult:
    def __init__(self, score: float, evidence: dict[str, Any]):
        self.score = score
        self.evidence = evidence


class SignalContext:
    def __init__(
        self,
        db_session: Any,
        redis_client: Any,
        graph: Any,
        alert_type_stats: dict[str, dict[str, int]] | None = None,
    ):
        self.db = db_session
        self.redis = redis_client
        self.graph = graph
        self.alert_type_stats = alert_type_stats if alert_type_stats is not None else {}


class Signal(Protocol):
    @property
    def name(self) -> str:
        """The canonical name of this signal."""
        ...

    def score(
        self, alert: Alert, incident: Incident, centroid: IncidentCentroid, context: SignalContext
    ) -> SignalResult:
        """
        Calculates the similarity score between an alert and an incident.
        The score should be between 0.0 and 1.0.
        Must evaluate against the incident's centroid, NOT via pairwise comparisons.
        """
        ...
