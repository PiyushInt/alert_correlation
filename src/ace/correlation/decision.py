from typing import Any

from ace.correlation.containment import check_containment
from ace.correlation.signals.base import IncidentCentroid, Signal, SignalContext
from ace.correlation.signals.cooccurrence import get_alert_type
from ace.correlation.text_normalise import extract_normalised_text
from ace.db.models.alerts import Alert
from ace.db.models.incidents import Incident


class DecisionResult:
    def __init__(
        self,
        incident: Incident | None,
        score: float,
        reason: str,
        refusals: list[dict[str, str]] | None = None,
        evaluations: list[dict[str, Any]] | None = None,
        is_capped: bool = False,
        signal_scores: dict[str, float] | None = None,
    ):
        self.incident = incident
        self.score = score
        self.reason = reason
        self.refusals = refusals if refusals is not None else []
        self.evaluations = evaluations if evaluations is not None else []
        self.is_capped = is_capped
        self.signal_scores = signal_scores


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
    best_signal_scores: dict[str, float] | None = None

    refusals = []
    evaluations = []

    for incident, members in candidate_incidents:
        containment = check_containment(alert, incident, members, context.graph)

        if not containment.allowed:
            refusals.append(
                {
                    "incident_id": str(incident.id),
                    "reason": containment.reason,
                }
            )
            continue

        # CENTROID, NOT ANY-MEMBER rule is structurally enforced here:
        # We do NOT pass `members` to the signals. We build the abstract centroid
        # representation of the incident, preventing signals from iterating members
        # and subverting the transitivity rules.

        centroid_texts = set()
        centroid_types = set()
        for a in members:
            centroid_texts.update(extract_normalised_text(a))
            centroid_types.add(get_alert_type(a))

        centroid = IncidentCentroid(
            component_ids={a.component_id for a in members if a.component_id},
            normalised_text=centroid_texts,
            alert_types=centroid_types,
            cooccurrence_stats=context.alert_type_stats,
        )

        total_score = 0.0
        signal_scores = {}
        for signal in signals:
            result = signal.score(alert, incident, centroid, context)
            total_score += result.score
            signal_scores[signal.name] = result.score

        evaluations.append(
            {"incident_id": str(incident.id), "scores": signal_scores, "total": total_score}
        )

        # In a real system with multiple signals we might average or weight them.
        # For now, we sum (and there's only 1 signal).
        # We assume 1 active signal for Phase 7.

        if total_score >= threshold and total_score > best_score:
            best_score = total_score
            best_incident = incident
            best_reason = f"Score {total_score:.2f} >= {threshold}"
            best_signal_scores = signal_scores

    if best_incident:
        return DecisionResult(
            best_incident,
            best_score,
            best_reason,
            refusals,
            evaluations,
            signal_scores=best_signal_scores,
        )

    return DecisionResult(
        None, 0.0, "No suitable incident found or all candidates refused", refusals, evaluations
    )
