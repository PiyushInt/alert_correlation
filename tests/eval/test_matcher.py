import os
import sys
import subprocess
import json
import pytest
from eval.matcher import (
    GroundTruthIncident,
    PredictedIncident,
    match_incidents,
    canonical_serialize_assignment,
)


def test_exact_match() -> None:
    gt = GroundTruthIncident(
        id="gt1", family="f1", alerts=frozenset({"A", "B"}), expected_root_cause="rc"
    )
    p = PredictedIncident(id="p1", alerts=frozenset({"A", "B"}), root_cause_ranked=("rc",))

    res = match_incidents([p], [gt])

    assert res.assignment == [(p, gt)]
    assert res.edges == [(p, gt)]
    assert res.over_split_participants == []
    assert res.over_merge_participants == []
    assert res.unmatched_predictions == []
    assert res.unmatched_ground_truths == []
    assert res.over_merges == []
    assert res.over_splits == []


def test_extra_alert() -> None:
    gt = GroundTruthIncident(
        id="gt1", family="f1", alerts=frozenset({"A", "B"}), expected_root_cause="rc"
    )
    p = PredictedIncident(id="p1", alerts=frozenset({"A", "B", "C"}), root_cause_ranked=("rc",))

    res = match_incidents([p], [gt])

    assert res.assignment == [(p, gt)]
    assert res.edges == [(p, gt)]


def test_over_split() -> None:
    gt = GroundTruthIncident(
        id="gt1", family="f1", alerts=frozenset({"A", "B", "C"}), expected_root_cause="rc"
    )
    p1 = PredictedIncident(id="p1", alerts=frozenset({"A", "B"}), root_cause_ranked=("rc",))
    p2 = PredictedIncident(id="p2", alerts=frozenset({"C"}), root_cause_ranked=("rc",))

    res = match_incidents([p1, p2], [gt])

    # p1 has higher overlap (2) than p2 (1), so p1 gets assignment
    assert res.assignment == [(p1, gt)]
    assert res.edges == [(p1, gt), (p2, gt)]

    # p2 is the losing prediction
    assert res.over_split_participants == [p2]
    # p2 must NOT be in unmatched predictions
    assert p2 not in res.unmatched_predictions
    assert res.unmatched_predictions == []

    assert res.over_splits == [(gt, [p1, p2])]
    assert res.over_merges == []


def test_over_merge() -> None:
    gt1 = GroundTruthIncident(
        id="gt1", family="f1", alerts=frozenset({"A", "B"}), expected_root_cause="rc"
    )
    gt2 = GroundTruthIncident(
        id="gt2", family="f1", alerts=frozenset({"C"}), expected_root_cause="rc"
    )
    p = PredictedIncident(id="p1", alerts=frozenset({"A", "B", "C"}), root_cause_ranked=("rc",))

    res = match_incidents([p], [gt1, gt2])

    # p has higher overlap with gt1 (2) than gt2 (1).
    assert res.assignment == [(p, gt1)]
    # We sort edges correctly (gt1, p1), then (gt2, p1)
    assert res.edges == [(p, gt1), (p, gt2)]

    # gt2 is the losing ground truth
    assert res.over_merge_participants == [gt2]
    # gt2 must NOT be in unmatched ground truths
    assert gt2 not in res.unmatched_ground_truths
    assert res.unmatched_ground_truths == []

    assert res.over_merges == [(p, [gt1, gt2])]
    assert res.over_splits == []


def test_unmatched_prediction() -> None:
    gt = GroundTruthIncident(
        id="gt1", family="f1", alerts=frozenset({"A"}), expected_root_cause="rc"
    )
    p = PredictedIncident(id="p1", alerts=frozenset({"B"}), root_cause_ranked=("rc",))

    res = match_incidents([p], [gt])
    assert res.assignment == []
    assert res.edges == []
    assert res.unmatched_predictions == [p]
    assert res.unmatched_ground_truths == [gt]


def test_unmatched_ground_truth() -> None:
    gt = GroundTruthIncident(
        id="gt1", family="f1", alerts=frozenset({"A"}), expected_root_cause="rc"
    )
    res = match_incidents([], [gt])
    assert res.assignment == []
    assert res.edges == []
    assert res.unmatched_ground_truths == [gt]
    assert res.unmatched_predictions == []


def test_determinism() -> None:
    fixture_code = """
import sys
import json
from eval.matcher import (
    GroundTruthIncident,
    PredictedIncident,
    match_incidents,
    canonical_serialize_assignment
)

gt1 = GroundTruthIncident(id="gt1", family="f1", alerts=frozenset({"A", "B"}), expected_root_cause="rc")
gt2 = GroundTruthIncident(id="gt2", family="f1", alerts=frozenset({"C", "D"}), expected_root_cause="rc")
p1 = PredictedIncident(id="p1", alerts=frozenset({"A", "B", "C"}), root_cause_ranked=("rc",))
p2 = PredictedIncident(id="p2", alerts=frozenset({"D"}), root_cause_ranked=("rc",))

res = match_incidents([p1, p2], [gt1, gt2])
out = canonical_serialize_assignment(res)
print(json.dumps(out))
"""
    env1 = os.environ.copy()
    env1["PYTHONHASHSEED"] = "1"

    env2 = os.environ.copy()
    env2["PYTHONHASHSEED"] = "2"

    proc1 = subprocess.run(
        [sys.executable, "-c", fixture_code], env=env1, capture_output=True, text=True, check=True
    )
    proc2 = subprocess.run(
        [sys.executable, "-c", fixture_code], env=env2, capture_output=True, text=True, check=True
    )

    assert proc1.stdout == proc2.stdout
