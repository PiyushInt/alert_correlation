from ace.correlation.signals.base import IncidentCentroid, Signal, SignalContext, SignalResult
from ace.db.models.alerts import Alert
from ace.db.models.incidents import Incident


class SameComponentSignal(Signal):
    def score(
        self, alert: Alert, incident: Incident, centroid: IncidentCentroid, context: SignalContext
    ) -> SignalResult:
        if alert.component_id is None:
            # NULL does not equal NULL in correlation logic
            return SignalResult(
                score=0.0, evidence={"match": False, "reason": "alert component is null"}
            )  # noqa: E501

        if alert.component_id in centroid.component_ids:
            return SignalResult(
                score=1.0, evidence={"match": True, "component_id": str(alert.component_id)}
            )

        return SignalResult(
            score=0.0, evidence={"match": False, "alert_component_id": str(alert.component_id)}
        )
