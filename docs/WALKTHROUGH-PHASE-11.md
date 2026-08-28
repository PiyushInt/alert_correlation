# Walkthrough: Phase 11 - Incident split, operator feedback, and the notification path

## 1. Rendered notification from a real capture
This demonstration was produced by rendering incident `1c476517-1ad6-42e7-a64c-8aebde09d822` directly via the application API. Its tools are one zabbix alert and two constructed.

> [!NOTE]
> This incident is contaminated with synthetic alerts (source_tool='constructed') as part of the Phase 10 ranking demonstration. It is still used here because it is one of the few multi-tool incidents available.

```text
=== INCIDENT NOTIFICATION [TRIGGERED] ===
Incident: 1c476517-1ad6-42e7-a64c-8aebde09d822
Title: Incident affecting 9171e0ed, f134e20d
Severity: high
State Banner: DEGRADED

MEMBER ALERTS:
 - constructed: 0bb3e917-0a23-404c-b838-2b096cb6b551 (8a0dd3dc-9959-49be-9df8-8b7eb853694a)
 - constructed: c39d8bcf-3681-448d-89a6-cfbbf0fe1b11 (7c2d37b4-4b16-4448-8fbe-4ce3f6500d12)
 - zabbix: 70cbec22-f21d-4690-b8f7-61fb614bfc1a (c28827f2ad12966d)

ROOT CAUSE CANDIDATES (Top 3):
 1. Component 9171e0ed-4870-4845-866e-fcc57d0a8100 Score: 9.00 (UNCERTAIN)
    Evidence: {'hops': 0.0, 'direction': 'self', 'fired_alert': True, 'is_earliest_alert': True}
 2. Component f134e20d-9752-4eac-bab8-b68a553f6ecd Score: 4.00 (UNCERTAIN)
    Evidence: {'hops': 0.0, 'direction': 'self', 'fired_alert': True, 'is_earliest_alert': False}
 3. Component 2a4e9cfc-f30c-4a42-a57c-c2b8a210f1f4 Score: 3.00 
    Evidence: {'hops': 1.0, 'direction': 'outbound', 'fired_alert': False, 'is_earliest_alert': False}

FEEDBACK API:
 POST /incidents/1c476517-1ad6-42e7-a64c-8aebde09d822/feedback
 {"verdict": "correct|wrong_group|missed_member|wrong_cause", "operator": "you"}
```

## 2. Dispatcher and ITSM idempotency
(Accepted in previous demonstration.) One notification file, one ITSM record, and correct skip on re-run.

## 3. Disagreement rate per signal
The disagreement rate metric (`ace_signal_disagreement_total`) is implemented in code but **cannot be meaningfully computed** on this estate today. 

The metric relies on operator feedback marking an incident as `wrong_group`, which is then tracked back to the signal that formed the grouping by reading `incident_alerts.signal_scores`. However, observation of the live estate reveals that `incident_alerts` contains 5 genuine `signal_scores` rows across 4 incidents, plus 1 fabricated row (issue 13) that must be excluded. With this statistically insignificant sample size, it is impossible to calculate meaningful signal disagreement rates on real historical data. The metric will begin to function only after new data flows through the pipeline and statistically significant signal scores are persisted.

## 4. Split alerts do not re-merge
For one partition's alerts to be re-evaluated against the other after a split, the existing member alerts would need to be re-ingested or explicitly sent back through the evaluation pipeline. The application **does not** offer a backfill or re-evaluation path for existing alerts. The pipeline only correlates new incoming alerts against existing incidents.

Therefore, the guarantee that split partitions do not re-merge is covered exclusively by the unit tests (which verify that identical incoming alert fingerprints hit the `split_suppressions` check and fail containment), rather than by observation of historical backfill on this estate.

## 5. GET /incidents/{id}/history
Demonstration on incident `991b1804-d7f2-45c4-af6e-6f6a400d180e` using the application's API:

```json
[
  {
    "type": "split",
    "created_at": "2026-08-28T09:31:44.080583+00:00",
    "reason": "Split by tool"
  }
]
```
