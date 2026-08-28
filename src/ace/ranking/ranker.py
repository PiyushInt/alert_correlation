import datetime
import logging
import uuid

from sqlalchemy.orm import Session

from ace.config import settings
from ace.db.models.alerts import Alert
from ace.db.models.incidents import Incident, IncidentAlert, RootCauseCandidate
from ace.dependency.graph import graph_instance
from ace.dependency.reachability import reachability

logger = logging.getLogger(__name__)


def rank_root_cause_candidates(
    db: Session, incident: Incident, current_time: datetime.datetime
) -> None:
    """
    Ranks root cause candidates for an incident.
    Persists them to root_cause_candidates table.
    """
    try:
        # Get all members of the incident
        member_links = (
            db.query(IncidentAlert).filter(IncidentAlert.incident_id == incident.id).all()
        )
        member_ids = [link.alert_id for link in member_links]
        members = db.query(Alert).filter(Alert.id.in_(member_ids)).all()

        if not members:
            return

        centroid_component_ids = {m.component_id for m in members if m.component_id}

        if not centroid_component_ids:
            return

        max_hops = settings.MAX_INCIDENT_HOPS

        # Timing analysis: find the earliest alert for each component involved in the incident
        component_earliest_times: dict[uuid.UUID, datetime.datetime] = {}
        for alert in members:
            if not alert.component_id:
                continue
            time_val = alert.starts_at or alert.received_at
            if (
                alert.component_id not in component_earliest_times
                or time_val < component_earliest_times[alert.component_id]
            ):
                component_earliest_times[alert.component_id] = time_val

        candidate_components = set(centroid_component_ids)
        for target_id in centroid_component_ids:
            neighbors = graph_instance.neighbours_within(target_id, max_hops, "both")
            candidate_components.update(neighbors)

        candidates_info: dict[uuid.UUID, tuple[float, str | None]] = {}
        for comp in candidate_components:
            best_hops = float("inf")
            best_direction = None

            for target_id in centroid_component_ids:
                res = reachability.get_shortest_path(comp, target_id)
                if res is not None:
                    hops, direction, path = res
                    if hops < best_hops:
                        best_hops = float(hops)
                        best_direction = direction

            if best_hops <= max_hops:
                candidates_info[comp] = (best_hops, best_direction)

        # Score the candidates
        scored_candidates = []
        for comp, (cand_hops, cand_direction) in candidates_info.items():
            score = 0.0

            # Base score based on direction (comp relative to centroid)
            # inbound: Centroid depends on this component (upstream). Very likely root cause.
            # outbound: This component depends on centroid (downstream). Likely a symptom.
            # self: No topological traversal, just a component that was in the incident.
            if cand_direction == "inbound":
                score += 20.0
            elif cand_direction == "outbound":
                score += 5.0
            elif cand_direction == "self":
                score += 2.0
            else:
                score += 1.0

            # Penalize by hops
            score -= cand_hops * 2.0

            is_earliest = False
            if component_earliest_times:
                earliest_time = min(component_earliest_times.values())
                if comp in component_earliest_times:
                    score += 2.0  # Bonus for actually having an alert
                    if component_earliest_times[comp] == earliest_time:
                        score += 5.0
                        is_earliest = True

            # 'uncertain' is True if there is no traversal evidence supporting the rank
            # (i.e. the candidate is just a 'self' centroid member with 0 hops,
            # not discovered via edges)
            uncertain = cand_direction == "self" or cand_hops == 0

            evidence = {
                "hops": cand_hops,
                "direction": cand_direction,
                "fired_alert": comp in component_earliest_times,
                "is_earliest_alert": is_earliest,
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
                computed_at=current_time,
            )
            db.add(candidate)

            # Wire the top-ranked candidate back to the parent incident
            if rank_idx == 0:
                incident.root_cause_component_id = comp

        db.commit()

    except Exception as e:
        db.rollback()
        logger.exception(f"Ranker failed for incident {incident.id}: {e}")
