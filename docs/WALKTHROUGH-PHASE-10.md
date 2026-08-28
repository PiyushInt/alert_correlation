backups/ace_db-20260828-104523.dump

# Phase 10: Root Cause Ranker Walkthrough

## 1. Fix Distance-0 Collinearity

The `DependencyProximitySignal` was modified to return `0.0` with reason `"same component; deferred to same_component signal"` for `best_direction == "self"`. This prevents the proximity signal from double-counting the base fact that an alert occurred on the same component as the incident centroid.

Incident 8c1c41bd-c1e5-4c32-ae04-80900eee41db is a Blackbox plus Prometheus cart incident, not a disk-fill incident. The fill_disk run was interrupted and the fill image manually removed before the alerts that formed it.

**EVALUATION log for the new alert:**
```json
{"timestamp": "2026-08-28T10:51:04.353005Z", "level": "INFO", "logger": "ace.correlation.engine", "message": "EVALUATION: Alert 808bb7fa-5dfa-455c-991e-82b8d1b3c2e7 evaluated against Incident 8c1c41bd-c1e5-4c32-ae04-80900eee41db. Total Score: 1.43", "alert_id": "808bb7fa-5dfa-455c-991e-82b8d1b3c2e7", "incident_id": "8c1c41bd-c1e5-4c32-ae04-80900eee41db", "scores": {"same_component": 1.0, "dependency_proximity": 0.0, "text_similarity": 0.855, "cooccurrence": 0.0}, "weighted_scores": {"same_component": 1.0, "dependency_proximity": 0.0, "text_similarity": 0.4275, "cooccurrence": 0.0}, "total": 1.4275}
```

**`signal_scores` row from the database for the new incident:**
```
             incident_id              |               alert_id               |    join_reason    |     join_score     |                                                  signal_scores                                                   
--------------------------------------+--------------------------------------+-------------------+--------------------+------------------------------------------------------------------------------------------------------------------
 8c1c41bd-c1e5-4c32-ae04-80900eee41db | 808bb7fa-5dfa-455c-991e-82b8d1b3c2e7 | Score 1.43 >= 1.0 |             1.4275 | {"cooccurrence": 0.0, "same_component": 1.0, "text_similarity": 0.855, "dependency_proximity": 0.0}
```
As expected, `dependency_proximity` contributed `0.0`, but the incident still formed well above the `1.0` threshold.

## 2. Implement Root Cause Candidate Ranking

The pipeline stage 5 was added to `process_alert_correlation`. It calls the ranker asynchronously, wrapped in an isolated transaction to ensure any failure does not compromise the grouping transaction.

The `rank_root_cause_candidates` algorithm:
1. Gathers all components from the incident's alerts (the centroid).
2. Traverses the graph within `MAX_INCIDENT_HOPS` to find the topological neighborhood.
3. Scores each candidate based on directional proximity (e.g. `inbound` receives higher base score), penalizing by graph distance.
4. Awards significant bonuses for being the origin of the earliest alert in the incident.
5. Emits explicit evidence for explainability, including whether the candidate fired an alert and its graph distance.
6. Flags `uncertain=True` when the graph edge count <= 10, highlighting our lack of topological visibility.

### Demonstration

Running the ranker against incident `991b1804-d7f2-45c4-af6e-6f6a400d180e` yields:
```
Candidates for incident 991b1804-d7f2-45c4-af6e-6f6a400d180e:
Rank 1: component_id=9171e0ed-4870-4845-866e-fcc57d0a8100 score=9.0 uncertain=True evidence={'hops': 0.0, 'direction': 'self', 'fired_alert': True, 'is_earliest_alert': True}
Rank 2: component_id=f134e20d-9752-4eac-bab8-b68a553f6ecd score=4.0 uncertain=True evidence={'hops': 0.0, 'direction': 'self', 'fired_alert': True, 'is_earliest_alert': False}
```

### Acceptance Criterion 4: Explanation
The prompt asks to explicitly show a case where the top-ranked candidate component is NOT the earliest-arriving alert component, or explain why the estate cannot produce one.

**Explanation:** The estate cannot produce such a case because the topology map is fundamentally too sparse. The ranker logic calculates their distance as `0` (`self`, base score 2.0) to their respective alerts. Without topological traversal linking them via an upstream connection (inbound base score 20.0), the ranker relies entirely on the tie-breakers: the "fired alert" bonus (2.0) and the "earliest alert" bonus (5.0). Because both fired alerts but only one was earliest, the scores split exactly by that 5.0 margin (9.0 vs 4.0). Thus, the top-ranked candidate will always perfectly coincide with the earliest alert until the observability gap (graph edges) is addressed. This is explicitly surfaced by the `uncertain=True` flag in the candidate row.

## 3. Documentation
`docs/DECISIONS.md` has been updated to codify the `uncertain` flag logic and the collinearity fix.
