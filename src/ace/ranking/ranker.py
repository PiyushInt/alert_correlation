import datetime
import logging

from sqlalchemy.orm import Session

from ace.config import settings
from ace.db.models.alerts import Alert
from ace.db.models.incidents import Incident, IncidentAlert, RootCauseCandidate
from ace.dependency.graph import graph_instance
from ace.dependency.reachability import reachability

logger = logging.getLogger(__name__)


def rank_root_cause_candidates(db: Session, incident: Incident, current_time: datetime.datetime) -> None:
    """
    Ranks root cause candidates for an incident.
    Persists them to root_cause_candidates table.
    """
    try:
        # Get all members of the incident
        member_links = db.query(IncidentAlert).filter(IncidentAlert.incident_id == incident.id).all()
        member_ids = [link.alert_id for link in member_links]
        members = db.query(Alert).filter(Alert.id.in_(member_ids)).all()

        if not members:
            return

        centroid_component_ids = {m.component_id for m in members if m.component_id}

        if not centroid_component_ids:
            return

        max_hops = settings.MAX_INCIDENT_HOPS

        # Timing analysis: find the earliest alert for each component involved in the incident
        component_earliest_times = {}
        for alert in members:
            if not alert.component_id:
                continue
            time_val = alert.starts_at or alert.received_at
            if alert.component_id not in component_earliest_times or time_val < component_earliest_times[alert.component_id]:
                component_earliest_times[alert.component_id] = time_val

        candidate_components = set(centroid_component_ids)
        for target_id in centroid_component_ids:
            neighbors = graph_instance.neighbours_within(target_id, max_hops, "both")
            candidate_components.update(neighbors)

        candidates_info = {}
        for comp in candidate_components:
            best_hops = float("inf")
            best_direction = None

            for target_id in centroid_component_ids:
                res = reachability.get_shortest_path(comp, target_id)
                if res is not None:
                    hops, direction, path = res
                    if hops < best_hops:
                        best_hops = hops
                        best_direction = direction

            if best_hops <= max_hops:
                candidates_info[comp] = {
                    "hops": best_hops,
                    "direction": best_direction
                }

        # Score the candidates
        scored_candidates = []
        for comp, info in candidates_info.items():
            score = 0.0
            
            # Base score based on direction (comp relative to centroid)
            # If comp is "inbound" to centroid (centroid DEPENDS ON comp), comp is upstream -> high probability of cause.
            if info["direction"] == "inbound":
                score += 10.0
            elif info["direction"] == "outbound":
                score += 5.0
            elif info["direction"] == "self":
                score += 8.0
            else:
                score += 3.0
                
            # Penalize by hops
            score -= info["hops"] * 2.0

            is_earliest = False
            if component_earliest_times:
                earliest_time = min(component_earliest_times.values())
                if comp in component_earliest_times:
                    score += 2.0  # Bonus for actually having an alert
                    if component_earliest_times[comp] == earliest_time:
                        score += 5.0
                        is_earliest = True

            uncertain = graph_instance.get_edge_count() <= 10

            evidence = {
                "hops": info["hops"],
                "direction": info["direction"],
                "fired_alert": comp in component_earliest_times,
                "is_earliest_alert": is_earliest
            }
            scored_candidates.append((score, comp, evidence, uncertain))

        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        
        for rank_idx, (score, comp, evidence, uncertain) in enumerate(scored_candidates):
            candidate = RootCauseCandidate(
                incident_id=incident.id,
                component_id=comp,
                rank=rank_idx + 1,
                score=score,
                evidence=evidence,
                uncertain=uncertain,
                computed_at=current_time
            )
            db.add(candidate)
            
        db.commit()

    except Exception as e:
        db.rollback()
        logger.exception(f"Ranker failed for incident {incident.id}: {e}")
