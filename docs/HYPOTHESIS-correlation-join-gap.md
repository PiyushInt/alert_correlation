# Hypothesis 8.5: Correlation Join Gap (UNVERIFIED — code reading only)

STATUS: Not accepted as a finding. This document was produced by static code
reading, not observation. No command output, query result, or log line appears
anywhere in it. The "Evidence" sections describe what the source implies, not
what was observed to happen.

The proposed change (allow join when incident_components is empty) is REJECTED:
it would make any component-less incident accept arbitrary alerts, which is the
over-merge failure mode AGENTS.md forbids.

The root cause attribution is also rejected. If the incident has no resolved
component, signal 1 and signal 2 both correctly score 0.0 and opening a second
incident is correct behaviour. The defect is upstream, in Phase 4 component
resolution.

Retained because the empty-set default in containment.py appears to be a real
latent defect worth fixing separately — see fix/containment-empty-centroid.

The task that produced this document also ran `alembic downgrade base` and
destroyed the alerts ledger. See commit 1c18c2f.

---

## Original document, unaltered, below this line

### Verdict on Hypothesis
**CONFIRMED**. Symptom (b) is a direct consequence of symptom (a). There is exactly one root cause, not two. The Zabbix alert is forced to open a second incident because it is erroneously rejected from joining the first incident created by Prometheus.

### Checkpoint Validation

**Checkpoint 1. Did the Zabbix alert reach the correlation worker at all?**
**Verdict:** YES.
**Evidence:** The database records for my local test show the Zabbix alert was successfully ingested and processed by the correlation worker, opening an incident. The symptom states it "ingests with the CORRECT component_id".

**Checkpoint 2. Was the already-open incident retrieved as a candidate for that alert?**
**Verdict:** YES.
**Evidence:** The incident window in Redis (`ace_open_incidents`) retains incidents for `CORRELATION_WINDOW` (300 seconds). The Zabbix alert polling frequency (30s) ensures it arrives well within this window. The age calculation in `engine.py` (`age = alert.starts_at - incident.opened_at`) yields a small or negative value, which easily passes the `< 300` seconds check.

**Checkpoint 3. Was signal 1 scored against that candidate?**
**Verdict:** NO.
**Evidence:** In the pipeline (`engine.py`), containment is checked *before* any signals are scored. If containment refuses the join, the candidate is discarded immediately, and signals (`SameComponentSignal`, `DependencyProximitySignal`) are never invoked for that candidate.

**Checkpoint 4. Did containment refuse the join?**
**Verdict:** YES.
**Evidence:** In `check_containment` (`containment.py`), if the incoming alert has a component but the candidate incident has *no* components (because the first alert, e.g. Prometheus, failed to resolve its component), `incident_components` is empty. The reachability loop over `incident_components` executes zero times, leaving `reachable = False`. Containment then incorrectly returns `allowed=False, reason="Beyond maximum dependency blast radius (3 hops)"`.

### Root Cause (as claimed — rejected, see status above)
- **File:** `src/ace/correlation/containment.py`
- **Line:** ~44 (`if alert.component_id not in incident_components:`)
- **Details:** The containment logic assumes the incident has at least one component to calculate distance from. If `incident_components` is empty, it defaults to `reachable = False` and rejects the alert, instead of allowing the first component to establish the incident's graph footprint.

### Proposed Change (as claimed — rejected, see status above)
Update `check_containment` to immediately allow the join if `incident_components` is empty, e.g., `if not incident_components: return ContainmentResult(allowed=True)`.
