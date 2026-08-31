import math
import pytest
from eval.labels import match_incidents, PipelineIncident, IncidentGroundTruth

def test_scorer_perfect_grouping():
    gt = [
        IncidentGroundTruth(
            description="test",
            firing_alerts=5,
            resolved_alerts=0,
            tools=["prometheus", "zabbix"],
            true_cause_component="comp-A"
        )
    ]
    
    pipeline = [
        PipelineIncident(
            id="inc-1",
            firing_alerts=5,
            tools=["prometheus", "zabbix"],
            root_cause_component="comp-A",
            top_3_candidates=["comp-B", "comp-A", "comp-C"]
        )
    ]
    
    result = match_incidents(pipeline, gt)
    assert result["precision"] == 1.0
    assert result["recall"] == 1.0
    assert result["over_merge_rate"] == 0.0
    assert result["root_cause_top3_rate"] == 1.0
    assert result["cross_tool_grouping"] == "Yes"

def test_scorer_under_grouping():
    gt = [
        IncidentGroundTruth(
            description="test",
            firing_alerts=8,
            resolved_alerts=0,
            tools=["prometheus", "blackbox"],
            true_cause_component="comp-A"
        )
    ]
    
    pipeline = [
        PipelineIncident(
            id="inc-1",
            firing_alerts=6,
            tools=["prometheus"],
            root_cause_component="comp-A",
            top_3_candidates=["comp-A"]
        ),
        PipelineIncident(
            id="inc-2",
            firing_alerts=2,
            tools=["blackbox"],
            root_cause_component="comp-A",
            top_3_candidates=["comp-A"]
        )
    ]
    
    result = match_incidents(pipeline, gt)
    
    assert result["precision"] == 1.0
    assert result["recall"] == 0.75
    assert result["over_merge_rate"] == 0.0

def test_scorer_over_merge():
    gt = [
        IncidentGroundTruth(
            description="test1",
            firing_alerts=2,
            resolved_alerts=0,
            tools=["prometheus"],
            true_cause_component="comp-A"
        ),
        IncidentGroundTruth(
            description="test2",
            firing_alerts=1,
            resolved_alerts=0,
            tools=["blackbox"],
            true_cause_component="comp-B"
        )
    ]
    
    pipeline = [
        PipelineIncident(
            id="inc-1",
            firing_alerts=3,
            tools=["prometheus", "blackbox"],
            root_cause_component="comp-A",
            top_3_candidates=["comp-A"]
        )
    ]
    
    result = match_incidents(pipeline, gt)
    
    assert math.isclose(result["precision"], 2/3)
    assert math.isclose(result["recall"], 2/3)
    assert result["over_merge_rate"] == 0.5
