# Open issues — deferred 2026-08-27, before Phase 9

Not blocking Phase 9. Each comes due at or before Gate B.

## 1. Summed signal scores against a 0.5 threshold
Signals are summed; each can reach 1.0. Any single signal firing clears the threshold
twice over. Observed 2026-08-27: signal 2 alone merged two unrelated alerts at 0.60.
This is a DESIGN DECISION, not a defect — resolve it in Phase 9 with all four signals
visible, not before.

## 2. Empty-centroid default in containment.py
Loop over an empty component set leaves reachable=False, producing a misleading refusal
reason. Real but never observed firing. See docs/HYPOTHESIS-correlation-join-gap.md.

## 3. exported_job unhandled
Field observed in Alertmanager payloads, deferred from Phase 8. Candidate contributor
to the unresolved-component rate.

## 4. Unresolved component rate 35% vs <5% target
Phase 0 baseline. A tuning target for Phase 13, not a defect. The estate may not be
able to do better; if so, say so rather than forcing the number.

## 5. Ledger contamination
32 alerts as of this date: real fault alerts, 9 constructed (source_tool='constructed'),
and older hand-posted test rows. Not fixable by editing — the ledger is append-only.
Phase 12 needs a clean run from fault injection only.

## 6. Component-count ambiguity
Task 8.11 reconciled the estate to three logical components receiving alerts. But the
2026-08-27 fault resolved both tools to /mnt/valkey-data, which is not among those
three. See docs/ESTATE.md.
- **Dedup Visibility Gap**: `ace/pipeline/dedup.py` drops duplicate alerts (incrementing `occurrence_count` in the database) without logging a `logger.info` or `logger.warning` message. This makes it appear as though an alert silently disappeared from the pipeline, causing diagnostic confusion.

## 7. Incorrect Blackbox Alert Rule Text
The Blackbox alert rule for the `cart` endpoint incorrectly contains the text `'Frontend is down (synthetic check)'` in its summary annotation. This is semantically wrong since it is probing the cart endpoint, not the frontend. This was observed during Phase 9 testing. Not a pipeline defect, but an estate configuration issue that should be fixed.

## 9. app.log grew to 120GB — rotation is broken with multiple writers
LOG_MAX_BYTES is 10MB with 3 backups, so the file should never exceed ~40MB. It reached
120GB and was deleted by hand on 2026-08-28.

Cause: RotatingFileHandler is not multi-process safe. The API and both workers each open
logs/app.log; when one rotates, the others continue writing to the deleted inode and the
size limit stops being enforced. Deleting the file also orphans every open descriptor,
which is why EVALUATION lines vanished after the delete until the workers were restarted.

Options: per-process log files (app-api.log, app-ingest.log, app-correlation.log), or a
WatchedFileHandler with external rotation, or stop relying on logs for durable evidence.

Related: issue 8. Per-signal scores must not live only in a log file.

## 8. Per-signal scores are not durable
EVALUATION log lines carry each signal's individual score, but incident_alerts stores
only join_reason and join_score — a single total. Incident bf547a82 joined at 2.5588 and
no record of the breakdown survives anywhere.

Phase 12 needs per-signal contribution to evaluate each signal separately, as AGENTS.md
requires. A log file is the wrong place for it: see issue 9. Proposed: add a
signal_scores JSONB column to incident_alerts, populated at join time. Needs a migration.
