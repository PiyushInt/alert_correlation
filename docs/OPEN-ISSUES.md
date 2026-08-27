# Open issues

Numbering is stable. Closed items stay listed so references in commit messages and PRs
resolve. Nothing here blocks the next phase; each comes due at or before Gate B.

## 1. Zabbix sends no recovery events — CLOSED 2026-08-28
The Zabbix action had empty Recovery operations, so no recovery event was ever sent.
Added by hand in the UI; both message templates now carry a status field. The adapter
reads PROBLEM -> firing, RESOLVED -> resolved. Fixed in PR #12.

NOTE: the action change is NOT exportable via configuration.export and must be
recreated by hand after any Zabbix reset. See docs/DECISIONS.md.

## 2. Summed signal scores against a 0.5 threshold — CLOSED 2026-08-28
Signals are summed; each can reach 1.0. Any single signal clearing 0.5 merges on its own.
Measured values on this estate: same_component 1.0, dependency_proximity 1.0 (0.6 on a
cross-component case), text_similarity 0.525, cooccurrence unmeasured.

Observed: signal 2 alone merged two unrelated alerts at 0.60. text_similarity at 0.525
would also merge on its own, with no component match and no proximity.

This is a design decision, not a defect. It is an input to Phase 10.

## 3. Empty-centroid default in containment.py — OPEN
Loop over an empty component set leaves reachable=False, producing a misleading refusal
reason. Real but never observed firing. See docs/HYPOTHESIS-correlation-join-gap.md.

## 4. exported_job unhandled — OPEN
Field observed in Alertmanager payloads, deferred from Phase 8. Candidate contributor to
the unresolved-component rate.

## 5. Unresolved component rate 35% vs <5% target — OPEN
Phase 0 baseline. A tuning target for Phase 13, not a defect. The estate may not be able
to do better; if so, say so rather than forcing the number.

## 6. Ledger contamination — OPEN
The alerts table mixes real fault alerts, 9 constructed rows (source_tool='constructed'),
and older hand-posted test rows. Not fixable by editing — the ledger is append-only.
Phase 12 needs a clean run from fault injection only.

## 7. Component-count ambiguity — OPEN
Task 8.11 reconciled the estate to three logical components receiving alerts. But faults
resolve both tools to /mnt/valkey-data, which is not among those three. See
docs/ESTATE.md.

## 8. Per-signal scores are not durable — CLOSED 2026-08-28
signal_scores JSONB column added to incident_alerts, populated at join time from
Signal.name keys. Existing rows left NULL; not backfilled. Fixed in PR #13.

## 9. app.log grew to 120GB — rotation is broken with multiple writers — OPEN
LOG_MAX_BYTES is 10MB with 3 backups, so the file should never exceed ~40MB. It reached
120GB and was deleted by hand on 2026-08-28.

Cause: RotatingFileHandler is not multi-process safe. The API and both workers each open
logs/app.log; when one rotates, the others continue writing to the deleted inode and the
size limit stops being enforced. Deleting the file also orphans every open descriptor,
which is why EVALUATION lines vanished until the workers were restarted.

Options: per-process log files, a WatchedFileHandler with external rotation, or stop
relying on logs for durable evidence. Issue 8 took the third route for signal scores.

## 10. Dedup logs nothing on a hit — OPEN
pipeline/dedup.py increments occurrence_count and drops the duplicate without logging.
An alert appears to vanish from the pipeline with no trace, which caused an hour of
misdiagnosis on 2026-08-27. A visibility gap, not a defect.

## 11. Blackbox cart rule has wrong summary text — OPEN
The Blackbox alert rule for the cart endpoint carries the annotation "Frontend is down
(synthetic check)". It probes cart, not frontend. An operator reading the notification
would be misled. Estate configuration, not a pipeline defect.
