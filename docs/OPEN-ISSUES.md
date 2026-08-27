# Open issues — deferred 2026-08-27, before Phase 9

Not blocking Phase 9. Each comes due at or before Gate B.

## 1. Zabbix sends no recovery events
One disk-fill fault: Prometheus resolved within four minutes, Zabbix sent nothing.
Zabbix also missed a second fault entirely (240s run). Multi-tool incidents therefore
cannot reach full resolution. Config investigation — see estate/zabbix/action_7.json.
Highest priority of the seven; the cross-tool premise depends on Zabbix firing reliably.
*(Note: A `kill_service` fault test correctly showed both Prometheus and Blackbox resolving, forming ONE incident, and auto-resolving successfully with `closed_at` set. This demonstrates the pipeline recovery path works flawlessly when the tool actually sends a resolve, strengthening the case that the Zabbix gap is a Zabbix configuration problem rather than ours).*

## 2. Summed signal scores against a 0.5 threshold
Signals are summed; each can reach 1.0. Any single signal firing clears the threshold
twice over. Observed 2026-08-27: signal 2 alone merged two unrelated alerts at 0.60.
This is a DESIGN DECISION, not a defect — resolve it in Phase 9 with all four signals
visible, not before.

## 3. Empty-centroid default in containment.py
Loop over an empty component set leaves reachable=False, producing a misleading refusal
reason. Real but never observed firing. See docs/HYPOTHESIS-correlation-join-gap.md.

## 4. exported_job unhandled
Field observed in Alertmanager payloads, deferred from Phase 8. Candidate contributor
to the unresolved-component rate.

## 5. Unresolved component rate 35% vs <5% target
Phase 0 baseline. A tuning target for Phase 13, not a defect. The estate may not be
able to do better; if so, say so rather than forcing the number.

## 6. Ledger contamination
32 alerts as of this date: real fault alerts, 9 constructed (source_tool='constructed'),
and older hand-posted test rows. Not fixable by editing — the ledger is append-only.
Phase 12 needs a clean run from fault injection only.

## 7. Component-count ambiguity
Task 8.11 reconciled the estate to three logical components receiving alerts. But the
2026-08-27 fault resolved both tools to /mnt/valkey-data, which is not among those
three. See docs/ESTATE.md.
- **Dedup Visibility Gap**: `ace/pipeline/dedup.py` drops duplicate alerts (incrementing `occurrence_count` in the database) without logging a `logger.info` or `logger.warning` message. This makes it appear as though an alert silently disappeared from the pipeline, causing diagnostic confusion.

## 8. Incorrect Blackbox Alert Rule Text
The Blackbox alert rule for the `cart` endpoint incorrectly contains the text `'Frontend is down (synthetic check)'` in its summary annotation. This is semantically wrong since it is probing the cart endpoint, not the frontend. This was observed during Phase 9 testing. Not a pipeline defect, but an estate configuration issue that should be fixed.
