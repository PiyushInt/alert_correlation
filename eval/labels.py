import yaml
import os
from dataclasses import dataclass
from typing import List, Dict, Any, Optional

@dataclass
class IncidentGroundTruth:
    description: str
    firing_alerts: int
    resolved_alerts: int
    tools: List[str]
    true_cause_component: str

@dataclass
class ScenarioGroundTruth:
    id: str
    family: str
    expected_incidents: List[IncidentGroundTruth]

def load_ground_truth(scenario_path: str) -> Optional[ScenarioGroundTruth]:
    if not os.path.exists(scenario_path):
        return None
    with open(scenario_path, "r") as f:
        data = yaml.safe_load(f)
        
    gt_data = data.get("ground_truth", {}).get("expected_incidents", [])
    incidents = []
    for item in gt_data:
        incidents.append(IncidentGroundTruth(
            description=item.get("description", ""),
            firing_alerts=item.get("firing_alerts", 0),
            resolved_alerts=item.get("resolved_alerts", 0),
            tools=item.get("tools", []),
            true_cause_component=item.get("true_cause_component", "")
        ))
        
    return ScenarioGroundTruth(
        id=data.get("id", ""),
        family=data.get("family", ""),
        expected_incidents=incidents
    )

@dataclass
class PipelineIncident:
    id: str
    firing_alerts: int
    tools: List[str]
    root_cause_component: str
    resolved_alerts: int = 0
    top_3_candidates: List[str] = None
    first_notification_delay: float = None  # None if not notified

def match_incidents(pipeline: List[PipelineIncident], gt: List[IncidentGroundTruth]) -> Dict[str, Any]:
    """
    Given a list of pipeline incidents and a list of ground truth incidents,
    computes grouping precision, grouping recall, over-merge rate, and root cause accuracy.
    """
    total_expected_alerts = sum(g.firing_alerts for g in gt)
    total_expected_incidents = len(gt)
    total_grouped_alerts = sum(p.firing_alerts for p in pipeline)
    
    true_positives_precision = 0
    true_positives_recall = 0
    over_merges = 0
    root_cause_hits = 0
    
    pipeline_to_gt = {}
    gt_to_pipelines = {i: [] for i in range(len(gt))}
    
    for p_idx, p in enumerate(pipeline):
        best_gt = -1
        best_score = -1
        
        for g_idx, g in enumerate(gt):
            score = 0
            if p.root_cause_component and g.true_cause_component and p.root_cause_component == g.true_cause_component:
                score += 10
            
            overlap = len(set(p.tools).intersection(set(g.tools)))
            score += overlap
            
            # Additional heuristic: if count matches closely, boost score
            count_diff = abs(p.firing_alerts - g.firing_alerts)
            if count_diff == 0:
                score += 5
            elif count_diff <= 2:
                score += 2
            
            if score > best_score:
                best_score = score
                best_gt = g_idx
                
        if best_gt != -1:
            pipeline_to_gt[p_idx] = best_gt
            gt_to_pipelines[best_gt].append(p_idx)
            
            if p.top_3_candidates and gt[best_gt].true_cause_component in p.top_3_candidates:
                root_cause_hits += 1

    for p_idx, p in enumerate(pipeline):
        g_idx = pipeline_to_gt.get(p_idx)
        if g_idx is not None:
            g = gt[g_idx]
            if p.firing_alerts > g.firing_alerts:
                over_merges += 1
                tp = g.firing_alerts
            else:
                tp = p.firing_alerts
            
            true_positives_precision += tp

    for g_idx, g in enumerate(gt):
        mapped_ps = gt_to_pipelines[g_idx]
        if not mapped_ps:
            continue
            
        largest_tp = 0
        for p_idx in mapped_ps:
            p = pipeline[p_idx]
            tp = min(p.firing_alerts, g.firing_alerts)
            if tp > largest_tp:
                largest_tp = tp
                
        true_positives_recall += largest_tp
        
    precision = (true_positives_precision / total_grouped_alerts) if total_grouped_alerts > 0 else 0.0
    recall = (true_positives_recall / total_expected_alerts) if total_expected_alerts > 0 else 0.0
    over_merge_rate = (over_merges / total_expected_incidents) if total_expected_incidents > 0 else 0.0
    root_cause_top3_rate = (root_cause_hits / len(pipeline)) if len(pipeline) > 0 else 0.0
    
    cross_tool = "No"
    for g_idx, g in enumerate(gt):
        if len(g.tools) > 1:
            mapped_ps = gt_to_pipelines[g_idx]
            for p_idx in mapped_ps:
                p = pipeline[p_idx]
                if len(set(p.tools)) > 1:
                    cross_tool = "Yes"
                    break
    
    return {
        "precision": precision,
        "recall": recall,
        "over_merge_rate": over_merge_rate,
        "root_cause_top3_rate": root_cause_top3_rate,
        "cross_tool_grouping": cross_tool,
        "total_expected_alerts": total_expected_alerts,
        "total_grouped_alerts": total_grouped_alerts
    }
