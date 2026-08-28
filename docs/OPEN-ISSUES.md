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
