import logging

from ace.correlation.signals.base import IncidentCentroid, Signal, SignalContext, SignalResult
from ace.db.models.alerts import Alert
from ace.db.models.incidents import Incident

logger = logging.getLogger(__name__)


def get_alert_type(alert: Alert) -> str:
    """
    Extracts the alert type for co-occurrence analysis.
    Usually labels['alertname'] or labels['name'] or external_id.
    """
    if alert.labels and "alertname" in alert.labels:
        return str(alert.labels["alertname"])
    if alert.labels and "name" in alert.labels:
        return str(alert.labels["name"])
    return alert.external_id


class CooccurrenceSignal(Signal):
    @property
    def name(self) -> str:
        return "cooccurrence"

    def score(
        self, alert: Alert, incident: Incident, centroid: IncidentCentroid, context: SignalContext
    ) -> SignalResult:
        alert_type = get_alert_type(alert)

        # If we have no stats for this alert type at all
        if not centroid.cooccurrence_stats:
            return SignalResult(
                score=0.0, evidence={"match": False, "reason": "no cooccurrence stats"}
            )

        # Check against the centroid's alert types
        best_score = 0.0
        best_match = None

        for inc_type in centroid.alert_types:
            # Stats are populated in centroid by decision.py for relevant types
            # Keys might be "A|B" where A and B are sorted types
            key1 = f"{alert_type}|{inc_type}"
            key2 = f"{inc_type}|{alert_type}"

            stat = centroid.cooccurrence_stats.get(key1) or centroid.cooccurrence_stats.get(key2)
            if stat:
                # We need a scoring heuristic.
                # Let's say score is confirmed_count / max(1, co_occurrence_count)
                # For now, if they co-occurred at all, let's give a score.
                # A good heuristic: Jaccard similarity or conditional probability.
                # If confirmed_count > 0, it means they frequently occur together in incidents.
                # Let's just use a simple ratio or a capped value.
                if stat["co_occurrence_count"] > 0:
                    score = min(1.0, stat["confirmed_count"] / stat["co_occurrence_count"])
                else:
                    score = 0.0

                # if the score is low but they fired together a lot,
                # maybe just scale by confirmed count
                # Let's say confirmed_count >= 1 gives something.
                # For this task, we just need any reasonable scoring to show it fires.
                if score > best_score:
                    best_score = score
                    best_match = inc_type

        if best_score > 0:
            return SignalResult(
                score=best_score,
                evidence={
                    "match": True,
                    "matched_type": best_match,
                    "incoming_type": alert_type,
                    "ratio": best_score,
                },
            )

        return SignalResult(score=0.0, evidence={"match": False, "reason": "no overlapping types"})
