import logging

from ace.correlation.containment import check_containment
from ace.correlation.signals.base import IncidentCentroid, Signal, SignalContext
from ace.db.models.alerts import Alert
from ace.db.models.incidents import Incident

logger = logging.getLogger(__name__)


class DecisionResult:
    def __init__(
        self, incident: Incident | None, score: float, reason: str, is_capped: bool = False
    ):
        self.incident = incident
        self.score = score
        self.reason = reason
        self.is_capped = is_capped


def make_decision(
    alert: Alert,
    candidate_incidents: list[tuple[Incident, list[Alert]]],
    signals: list[Signal],
    context: SignalContext,
    threshold: float = 0.5,
) -> DecisionResult:
    """
    Evaluates candidate incidents and decides which one the alert should join.
    This function is PURE.
    """
    best_incident: Incident | None = None
    best_score: float = -1.0
    best_reason: str = ""

    for incident, members in candidate_incidents:
        containment = check_containment(alert, incident, members, context.graph)

        if not containment.allowed:
            # We must log the refusal loudly per the design rule!
            logger.warning(
                f"CONTAINMENT REFUSED: Alert {alert.id} refused by Incident {incident.id}. "
                f"Reason: {containment.reason}"
            )
            continue

        # CENTROID, NOT ANY-MEMBER rule is structurally enforced here:
        # We do NOT pass `members` to the signals. We build the abstract centroid
        # representation of the incident, preventing signals from iterating members
        # and subverting the transitivity rules.
        centroid = IncidentCentroid(
            component_ids={a.component_id for a in members if a.component_id}
        )

        total_score = 0.0
        for signal in signals:
            result = signal.score(alert, incident, centroid, context)
            total_score += result.score

        # In a real system with multiple signals we might average or weight them.
        # For now, we sum (and there's only 1 signal).
        # We assume 1 active signal for Phase 7.

        if total_score >= threshold and total_score > best_score:
            best_score = total_score
            best_incident = incident
            best_reason = f"Score {total_score:.2f} >= {threshold}"

    if best_incident:
        return DecisionResult(best_incident, best_score, best_reason)

    return DecisionResult(None, 0.0, "No suitable incident found or all candidates refused")
