import uuid
from typing import Protocol

from ace.config import settings
from ace.db.models.alerts import Alert
from ace.db.models.incidents import Incident


class ContainmentResult:
    def __init__(self, allowed: bool, reason: str = ""):
        self.allowed = allowed
        self.reason = reason


class GraphProtocol(Protocol):
    def shortest_path_length(self, source: uuid.UUID, target: uuid.UUID) -> int: ...


def check_containment(
    alert: Alert, incident: Incident, incident_alerts: list[Alert], graph: GraphProtocol
) -> ContainmentResult:
    """
    Evaluates whether an alert is allowed to join an incident based on containment rules.
    This function is PURE (no I/O, no random, no clocks).
    """
    # 1. HARD PARTITIONS
    if alert.environment != incident_alerts[0].environment:
        return ContainmentResult(False, "Hard Partition: Environment mismatch")

    if alert.tenant != incident_alerts[0].tenant:
        return ContainmentResult(False, "Hard Partition: Tenant mismatch")

    # 2. SIZE CAP
    if len(incident_alerts) >= settings.MAX_INCIDENT_ALERTS:
        return ContainmentResult(False, "Size Cap: Incident has reached MAX_INCIDENT_ALERTS")

    # 3. DIAMETER CAP
    # If the alert doesn't have a component, it doesn't expand the graph footprint
    if alert.component_id is not None:
        incident_components = {
            a.component_id for a in incident_alerts if a.component_id is not None
        }
        if alert.component_id not in incident_components:
            # We must check if adding this component pushes the maximum pairwise distance
            # between any two components in the set {incident_components U alert.component_id}
            # over MAX_INCIDENT_HOPS.
            new_set = incident_components | {alert.component_id}

            # If there's only 1 component, diameter is 0.
            if len(new_set) > 1:
                # Calculate maximum shortest path between all pairs
                # (For very large sets, this could be expensive, but MAX_INCIDENT_HOPS and
                # MAX_INCIDENT_ALERTS bound it).
                max_hops = 0
                components_list = list(new_set)
                for i in range(len(components_list)):
                    for j in range(i + 1, len(components_list)):
                        try:
                            dist = graph.shortest_path_length(
                                components_list[i], components_list[j]
                            )
                            if dist > max_hops:
                                max_hops = dist
                        except Exception:
                            # No path exists, effectively infinite hops (disconnected).
                            # If they are disconnected, the diameter is infinite, breach.
                            return ContainmentResult(
                                False, "Diameter Cap: Components are disconnected in graph"
                            )  # noqa: E501

                if max_hops > settings.MAX_INCIDENT_HOPS:
                    return ContainmentResult(
                        False,
                        f"Diameter Cap: Adding component increases diameter to {max_hops} (max {settings.MAX_INCIDENT_HOPS})",  # noqa: E501
                    )

    # 4 & 5: CENTROID and NO TRANSITIVE CLOSURE are structural rules enforced by
    # decision.py evaluating the incident as a whole (centroid) via signal.score(),
    # rather than finding a pairwise match. There is no connected-component checking here.

    return ContainmentResult(True, "Allowed")
