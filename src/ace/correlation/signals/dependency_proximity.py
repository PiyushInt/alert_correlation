import logging

from ace.config import settings
from ace.correlation.signals.base import IncidentCentroid, Signal, SignalContext, SignalResult
from ace.db.models.alerts import Alert
from ace.db.models.incidents import Incident
from ace.dependency.reachability import reachability

logger = logging.getLogger(__name__)


class DependencyProximitySignal(Signal):
    @property
    def name(self) -> str:
        return "dependency_proximity"

    def score(
        self, alert: Alert, incident: Incident, centroid: IncidentCentroid, context: SignalContext
    ) -> SignalResult:
        if alert.component_id is None:
            return SignalResult(
                score=0.0, evidence={"match": False, "reason": "alert component is null"}
            )

        edge_count = context.graph.get_edge_count()
        if edge_count == 0:
            return SignalResult(
                score=0.0, evidence={"match": False, "reason": "map is stale/empty"}
            )

        best_hops = float("inf")
        best_direction = None
        best_path = None
        best_target = None

        # CENTROID, NOT ANY-MEMBER: distance is measured from the incident's component SET
        for target_id in centroid.component_ids:
            res = reachability.get_shortest_path(alert.component_id, target_id)
            if res is not None:
                hops, direction, path = res
                if hops < best_hops:
                    best_hops = hops
                    best_direction = direction
                    best_path = path
                    best_target = target_id

        if best_hops == float("inf"):
            return SignalResult(score=0.0, evidence={"match": False, "reason": "no path found"})

        if best_hops > settings.MAX_INCIDENT_HOPS:
            return SignalResult(
                score=0.0, evidence={"match": False, "reason": "path exceeds max hops"}
            )

        # Base weight based on direction
        if best_direction == "outbound":
            # Alert DEPENDS ON incident
            base_score = settings.PROXIMITY_WEIGHT_OUTBOUND
        elif best_direction == "inbound":
            # Incident DEPENDS ON alert
            base_score = settings.PROXIMITY_WEIGHT_INBOUND
        elif best_direction == "self":
            base_score = 1.0
        else:
            base_score = min(settings.PROXIMITY_WEIGHT_INBOUND, settings.PROXIMITY_WEIGHT_OUTBOUND)

        # Decay based on hops beyond 1.
        # e.g. 1 hop = base_score * (decay^0)
        decay = settings.PROXIMITY_DECAY_RATE ** max(0, best_hops - 1)
        final_score = base_score * decay

        # Trace vs Inventory
        is_trace = False
        is_inventory = False
        if best_path and len(best_path) > 1:
            for i in range(len(best_path) - 1):
                u, v = best_path[i], best_path[i + 1]
                edge_data = context.graph.get_edge_data(u, v)
                if not edge_data:
                    edge_data = context.graph.get_edge_data(v, u)

                if edge_data:
                    source = edge_data.get("source", "unknown")
                    if source == "trace":
                        is_trace = True
                    elif source == "inventory":
                        is_inventory = True

        path_type = "mixed"
        if is_trace and not is_inventory:
            path_type = "trace"
        elif is_inventory and not is_trace:
            path_type = "inventory"

        evidence = {
            "match": True,
            "hops": best_hops,
            "direction": best_direction,
            "path": [str(p) for p in best_path] if best_path else [],
            "path_type": path_type,
            "target_component_id": str(best_target),
        }

        return SignalResult(score=final_score, evidence=evidence)
