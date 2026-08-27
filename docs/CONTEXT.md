# Context and Operating Evidence

**No Production Access**
There is no production alert feed available. The local OpenTelemetry Demo estate is the entire evidence base. All metrics, throughput claims, and sizing numbers represent the engine's performance under injected faults in this synthetic environment.

**Build vs Buy**
This pattern is implemented commercially by ServiceNow ITOM, BigPanda, Moogsoft, and Dynatrace Davis. This project demonstrates a custom, cross-tool correlation engine using open-source primitives.

**Resource Constraints & Limitations**
Due to memory constraints and service breakage, the following adjustments define the estate's boundaries:
- **Removed Services**: 
  - `product-catalog`: Removed due to unresolvable crash-loops (cause unknown, distroless image makes it undiagnosable).
  - `cadvisor`: Removed for memory overhead and port conflicts.
  - `toxiproxy`: Removed for memory overhead.
- **Excluded Services**: Because `product-catalog` is missing, the `checkout` service permanently returns 500s. It is completely excluded from all measurements and rules.
- **Missing Metrics**: There are no service-level latency metrics available on `cart`, so the `HighLatency` rule was cut.
- **Blackbox Probing Gap**: Blackbox does not detect partial degradation. The frontend will happily return a 200 OK even if the backend `cart` service is completely broken.

**Measurement Characteristics**
- **Detection Lag**: There is a ~2 minute detection lag built into the estate due to `metric_expiration: 60s` in the OpenTelemetry collector plus `for: 1m` in Prometheus rules.
- **Scope**: Exactly 4 fault types are measured against one single topology, using one labeller.
- **Baseline Unresolved Components**: The estate currently has **35% unresolved component identifiers** at baseline. This is the official starting point that Phase 4's resolver must improve upon to hit the `<5%` target.

**Dependency Map Limitations (Phase 6)**
The core of the project was described as being "built from observed traffic" via OTLP traces. However, the OpenTelemetry demo estate has severe limitations in emitting client spans:
- The OTel Demo's frontend does not emit client spans for its backend calls in this configuration, so service-to-service edges below the entry point are invisible to trace extraction.
- Datastore calls from cart emit no spans at all.
- Trace extraction therefore observed only the edges it could: `load-generator -> frontend`.
- Everything on the headline chain is inventory-seeded.

The headline chain is composed as follows:
- `frontend -> cart`: inventory (seeded)
- `cart -> valkey`: inventory (seeded)
- `valkey -> docker-host-01`: inventory (seeded)
- `docker-host-01 -> /mnt/valkey-data`: inventory (seeded)

0 of 4 edges on the critical path are observed from traces. This represents a significant limitation of trace-derived maps in this estate.

## The alerts ledger was mutable from Phase 5 to Phase 8

Until 2026-08-27, dedup.py overwrote the firing alert row when a resolve arrived,
setting status to 'resolved' and ends_at to the fire time. No firing alert survived
its own resolution. A count of firing Prometheus alerts in the ledger returned 0.

Consequences that cannot be undone:
- Phase 0's operating envelope (duplicate rate, alerts per fault, unresolved rate)
  was measured against a table that erased firing history.
- Any grouping or noise-reduction figure computed over alert counts before this
  date is unreliable.
- The original Gate A record carried the same defect and was subsequently destroyed
  by an agent running `alembic downgrade base` during a read-only investigation.
  Gate A has since been reproduced: one disk-fill fault, Prometheus and Zabbix,
  divergent identifiers, one incident with source_tool_count = 2.

The defect was found by investigating a symptom in correlation, four stages
downstream of its cause. Green CI and passing unit tests did not catch it at any
point across four phases.

## Zabbix does not send recovery events

Verified 2026-08-27 by hand. A disk-fill fault produced firing alerts from both
Prometheus and Zabbix. When the fault cleared, Prometheus sent a resolve within four
minutes. Zabbix sent nothing — one webhook total for the whole fault, the firing one,
twenty minutes after the disk returned to 1%.

Not yet established whether the Zabbix trigger failed to recover, or recovered but the
action has no recovery operation configured. See estate/zabbix/action_7.json.

Consequence: in the cross-tool case this project exists to demonstrate, incidents
cannot reach full resolution. Every multi-tool incident stays open indefinitely, held
by the unresolved Zabbix member. Full-resolution auto-close and window-expiry closure
are untestable against this estate as configured.
