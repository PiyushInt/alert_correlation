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
In Phase 10, the record was corrected to reflect that `CORRELATION_THRESHOLD` has defaulted to 1.0 throughout, and weights were introduced in PR #14.
Observed: The claim that signal 2 alone successfully merged two unrelated alerts at 0.60 (or 0.525) was an unverified false positive. At threshold 1.0 with a weight of 0.5, a score of 0.525 contributes 0.2625 and cannot merge anything on its own. Circumstantial signals require corroboration under the actual weighting scheme.

This is a design decision implemented in Phase 10.

## 3. Empty centroid default fails containment with incorrect reason — CLOSED
In containment.py, if the candidate incident has no resolved components, the incoming alert is now correctly refused if it has a component, returning the reason "Empty Centroid: Incident has no resolved components to calculate distance against".

## 4. exported_job unhandled — OPEN
Field observed in Alertmanager payloads, deferred from Phase 8. Candidate contributor to
the unresolved-component rate.

## 5. Unresolved component rate 35% vs <5% target — OPEN
Phase 0 baseline. A tuning target for Phase 13, not a defect. The estate may not be able
to do better; if so, say so rather than forcing the number.

## 6. Ledger contamination — OPEN
The alerts table mixes real fault alerts, 12 constructed rows (source_tool='constructed'),
and older hand-posted test rows. Not fixable by editing — the ledger is append-only.
This contamination affects headline metrics: incident 991b1804 (the only three-tool incident, used for Phase 10 ranking demonstration) includes two `constructed` alerts (`0bb3e917-0a23-404c-b838-2b096cb6b551` and `c39d8bcf-3681-448d-89a6-cfbbf0fe1b11`). Its source_tool_count=3 counted a synthetic row as a monitoring tool.
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

## 10. Dedup logs nothing on a hit — CLOSED
pipeline/dedup.py now logs at INFO on every deduplication hit, recording the incoming alert ID, the original alert ID, the fingerprint, and the updated occurrence_count.

## 11. Blackbox cart rule has wrong summary text — CLOSED
The Blackbox alert rule for the cart endpoint carried the annotation "Frontend is down (synthetic check)". It has been corrected to "Cart is down (synthetic check)". Estate configuration updated.

## 12. Destruction of root_cause_candidates history for 991b1804 — OPEN
On 2026-08-28, an ad-hoc script executed DELETE against `root_cause_candidates` for incident 991b1804, destroying all prior candidate sets including pipeline-generated ones. Two rows remain with a single `computed_at`. The append-only versioning Phase 10 was designed to demonstrate can no longer be shown from the database for that incident. This is deliberately not restored to keep the ledger internally consistent with the alerts table.

## 13. Fabricated signal scores row — OPEN
The `incident_alerts` table contains one fabricated `signal_scores` row written by a demo script on 2026-08-28. 
Row ID: `c9598adf-b1ca-4d06-bc43-4d0a006b32a7`
Incident ID: `de28d185-308f-4d21-8fa4-5f3c4b3316bc`
Alert ID: `161b32fa-5d01-4a65-a9f2-d3d366e8108e`
`signal_scores`: `{"text_similarity": 0.9, "dependency_proximity": 0.8}`
It is identifiable by its shape (two keys only, missing `same_component` and `cooccurrence`) and its round values. Any computation over `signal_scores` must explicitly exclude this row.

## 14. Ranker output is not wired to incidents.root_cause_component_id — OPEN
The root cause ranker built in Phase 10 correctly computes and writes candidates to the `root_cause_candidates` table. However, it never updates the parent `Incident` record's `root_cause_component_id` column to reflect the top-ranked candidate. 
Evidence: During evaluation replays, incidents generated correctly received 8 candidates each in the `ace_db_eval` database's `root_cause_candidates` table, but querying the resulting incident always returns `root_cause_component_id` as null. As a result, no consumer can read the ranking directly from the incident. This is a pipeline behavior defect and will be addressed in a separate change outside of Phase 12a.

## 15. Resolution fails if fault duration exceeds DEDUP_WINDOW — OPEN
Because resolution matching in `src/ace/pipeline/dedup.py` relies exclusively on the Redis dedup cache (`r.get(dedup_key)`) to map a resolution alert to its firing original, any fault that lasts longer than `DEDUP_WINDOW` will never resolve its incident. The firing alert's dedup key will expire, and when the resolution alert finally arrives, the pipeline cannot link it, leaving the incident stuck in the `open` state indefinitely. The default window is 3600s, meaning any production fault lasting over an hour (e.g., a slow-burn disk fill) will trigger this defect.
