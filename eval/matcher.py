from dataclasses import dataclass

# A prediction sharing a single alert with a ground truth can never be an
# unmatched prediction, so precision in task 2 must be computed on alert
# membership within the assigned pair. Metrics are computed over `assignment`,
# never `edges`.
MIN_OVERLAP = 1

@dataclass(frozen=True)
class GroundTruthIncident:
    id: str
    family: str
    alerts: frozenset[str]
    expected_root_cause: str

@dataclass(frozen=True)
class PredictedIncident:
    id: str
    alerts: frozenset[str]
    root_cause_ranked: tuple[str, ...]

@dataclass(frozen=True)
class AssignmentResult:
    # Key: (ground_truth.id, prediction.id)
    edges: list[tuple[PredictedIncident, GroundTruthIncident]]
    
    # Key: (ground_truth.id, prediction.id)
    assignment: list[tuple[PredictedIncident, GroundTruthIncident]]
    
    # Key: prediction.id
    over_split_participants: list[PredictedIncident]
    
    # Key: ground_truth.id
    over_merge_participants: list[GroundTruthIncident]
    
    # Key: prediction.id
    unmatched_predictions: list[PredictedIncident]
    
    # Key: ground_truth.id
    unmatched_ground_truths: list[GroundTruthIncident]
    
    # Key: outer prediction.id; inner ground truths sort on id
    over_merges: list[tuple[PredictedIncident, list[GroundTruthIncident]]]
    
    # Key: outer ground_truth.id; inner predictions sort on id
    over_splits: list[tuple[GroundTruthIncident, list[PredictedIncident]]]


def _compute_assignments(
    pred_alerts: dict[str, frozenset[str]],
    gt_alerts: dict[str, frozenset[str]]
) -> tuple[
    list[tuple[str, str]],
    list[tuple[str, str]],
    list[str],
    list[str],
    list[str],
    list[str],
    list[tuple[str, list[str]]],
    list[tuple[str, list[str]]]
]:
    edges: list[tuple[str, str]] = []
    # prediction id -> list of matched ground truth ids
    pred_to_gts: dict[str, list[str]] = {p_id: [] for p_id in pred_alerts}
    # ground truth id -> list of matched prediction ids
    gt_to_preds: dict[str, list[str]] = {gt_id: [] for gt_id in gt_alerts}

    for p_id, p_set in pred_alerts.items():
        for gt_id, gt_set in gt_alerts.items():
            if len(p_set & gt_set) >= MIN_OVERLAP:
                edges.append((p_id, gt_id))
                pred_to_gts[p_id].append(gt_id)
                gt_to_preds[gt_id].append(p_id)

    # Sort all edges under a total order for global matching
    # overlap size descending, then ground-truth id, then prediction id
    def edge_sort_key(edge: tuple[str, str]) -> tuple[int, str, str]:
        p_id, gt_id = edge
        overlap_size = len(pred_alerts[p_id] & gt_alerts[gt_id])
        return (-overlap_size, gt_id, p_id)
    
    sorted_edges = sorted(edges, key=edge_sort_key)
    
    assignment: list[tuple[str, str]] = []
    assigned_preds = set()
    assigned_gts = set()
    
    for p_id, gt_id in sorted_edges:
        if p_id not in assigned_preds and gt_id not in assigned_gts:
            assignment.append((p_id, gt_id))
            assigned_preds.add(p_id)
            assigned_gts.add(gt_id)

    over_split_participants: list[str] = []
    over_merge_participants: list[str] = []
    
    over_merges: list[tuple[str, list[str]]] = []
    over_splits: list[tuple[str, list[str]]] = []
    
    unmatched_predictions: list[str] = []
    unmatched_ground_truths: list[str] = []

    for p_id in pred_alerts:
        matched_gts = pred_to_gts[p_id]
        if not matched_gts:
            unmatched_predictions.append(p_id)
        else:
            if p_id not in assigned_preds:
                over_split_participants.append(p_id)
            if len(matched_gts) > 1:
                # Prediction claimed more than 1 GT
                over_merges.append((p_id, sorted(matched_gts)))
                
    for gt_id in gt_alerts:
        matched_preds = gt_to_preds[gt_id]
        if not matched_preds:
            unmatched_ground_truths.append(gt_id)
        else:
            if gt_id not in assigned_gts:
                over_merge_participants.append(gt_id)
            if len(matched_preds) > 1:
                # GT claimed by more than 1 prediction
                over_splits.append((gt_id, sorted(matched_preds)))

    # Sort everything as requested
    edges_out = sorted(edges, key=lambda e: (e[1], e[0]))
    assignment_out = sorted(assignment, key=lambda e: (e[1], e[0]))
    over_split_participants_out = sorted(over_split_participants)
    over_merge_participants_out = sorted(over_merge_participants)
    unmatched_predictions_out = sorted(unmatched_predictions)
    unmatched_ground_truths_out = sorted(unmatched_ground_truths)
    over_merges_out = sorted(over_merges, key=lambda x: x[0])
    over_splits_out = sorted(over_splits, key=lambda x: x[0])

    return (
        edges_out,
        assignment_out,
        over_split_participants_out,
        over_merge_participants_out,
        unmatched_predictions_out,
        unmatched_ground_truths_out,
        over_merges_out,
        over_splits_out
    )

def match_incidents(
    predictions: list[PredictedIncident],
    ground_truths: list[GroundTruthIncident]
) -> AssignmentResult:
    pred_map = {p.id: p for p in predictions}
    gt_map = {gt.id: gt for gt in ground_truths}
    
    pred_alerts = {p.id: p.alerts for p in predictions}
    gt_alerts = {gt.id: gt.alerts for gt in ground_truths}
    
    res = _compute_assignments(pred_alerts, gt_alerts)
    (
        raw_edges,
        raw_assignment,
        raw_osp,
        raw_omp,
        raw_up,
        raw_ugt,
        raw_om,
        raw_os
    ) = res
    
    return AssignmentResult(
        edges=[(pred_map[p], gt_map[gt]) for p, gt in raw_edges],
        assignment=[(pred_map[p], gt_map[gt]) for p, gt in raw_assignment],
        over_split_participants=[pred_map[p] for p in raw_osp],
        over_merge_participants=[gt_map[gt] for gt in raw_omp],
        unmatched_predictions=[pred_map[p] for p in raw_up],
        unmatched_ground_truths=[gt_map[gt] for gt in raw_ugt],
        over_merges=[(pred_map[p], [gt_map[gt] for gt in gts]) for p, gts in raw_om],
        over_splits=[(gt_map[gt], [pred_map[p] for p in ps]) for gt, ps in raw_os],
    )

from typing import Any

def canonical_serialize_assignment(result: AssignmentResult) -> dict[str, Any]:
    # Serializes AssignmentResult to a dict comparing sorted lists of alerts.
    def serialize_pred(p: PredictedIncident) -> dict[str, Any]:
        return {"id": p.id, "alerts": sorted(list(p.alerts)), "root_cause_ranked": list(p.root_cause_ranked)}
        
    def serialize_gt(gt: GroundTruthIncident) -> dict[str, Any]:
        return {"id": gt.id, "family": gt.family, "alerts": sorted(list(gt.alerts)), "expected_root_cause": gt.expected_root_cause}

    # Returning in a structure that uses lists and dicts
    return {
        "edges": [{"p": serialize_pred(p), "gt": serialize_gt(gt)} for p, gt in result.edges],
        "assignment": [{"p": serialize_pred(p), "gt": serialize_gt(gt)} for p, gt in result.assignment],
        "over_split_participants": [serialize_pred(p) for p in result.over_split_participants],
        "over_merge_participants": [serialize_gt(gt) for gt in result.over_merge_participants],
        "unmatched_predictions": [serialize_pred(p) for p in result.unmatched_predictions],
        "unmatched_ground_truths": [serialize_gt(gt) for gt in result.unmatched_ground_truths],
        "over_merges": [{"p": serialize_pred(p), "gts": [serialize_gt(gt) for gt in gts]} for p, gts in result.over_merges],
        "over_splits": [{"gt": serialize_gt(gt), "ps": [serialize_pred(p) for p in ps]} for gt, ps in result.over_splits]
    }
