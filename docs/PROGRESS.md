# Progress Log

### Phase 1 - Repo Skeleton and Quality Gates
Established the strict `src/ace` layout defined in AGENTS.md with completely empty modules. Configured `pyproject.toml` with pinned dependencies, unified tool configs (ruff, mypy, pytest), and automated CI using GitHub Actions. Implemented strict git hooks and health check endpoints for robust quality gates. Bootstrapped PostgreSQL 16 and Redis 7 as local backing services with explicit health checks.

### Phase 3 - Alertmanager Ingestion and Fail-Open Bypass
Implemented the Alertmanager webhook, severity mapping, and the full
persist-first-then-publish pipeline. Added fail-open bypass: when Redis is
down, alerts are persisted to Postgres and written to the notifications/
directory as JSON files. Verified with manual tests that alerts survive Redis
outages. Added `component_unresolved` boolean column for tracking resolution
rate.

### Phase 4 - Zabbix/Blackbox Ingestion and Cross-Tool Identity Resolution
Implemented ZabbixAdapter, Resolver, and component seeding from
`estate/inventory/components.yaml`. Introduced the extraction contract:
each adapter implements `extract_identifiers(alert) -> list[Candidate]`,
resolution uses two passes (exact/alias then fuzzy), and the resolver
contains no tool-specific names.

#### Unresolved Rate After Seeding

Replaying all 38 accepted captured payloads (34 Alertmanager, 4 Zabbix)
against 3 seeded components:

| Metric | Value |
|---|---|
| Total alerts ingested | 41 |
| Resolved | 29 |
| Unresolved | 12 |
| **Unresolved rate** | **29.27%** |
| Phase 0 baseline | 35% (measured) |
| Target | < 5% |

**Breakdown by source tool:**

| Source tool | Total | Unresolved |
|---|---|---|
| blackbox | 11 | 0 |
| prometheus | 26 | 12 |
| zabbix | 4 | 0 |

**Unresolved alerts by alertname:**

| Alertname | Count | Reason |
|---|---|---|
| HighErrorRate | 6 | `otel-collector:8889` not in component inventory |
| CartDown (pre-label) | 6 | Fired before static `component: cart` label was added to rules.yml; no resolvable identifier |

**Why 29.27% is above the < 5% target:**
We seeded 3 components (`/mnt/valkey-data`, `docker-host-01`, `cart`). The
captures reference at least one more (`otel-collector:8889`) that is not
seeded. Closing the gap requires:
1. Adding `otel-collector` to `components.yaml` with alias
   `otel-collector:8889` for source_tool `prometheus`.
2. The 6 pre-label CartDown alerts are a historical artifact — future
   CartDown alerts carry `component: cart` and resolve correctly. These
   would not count in a production deployment.

With both changes, unresolved rate on the captured data would be **0%**.

#### Cross-Tool Identity Resolution Cases

**Case (a) — Shared-string (demonstrated on real captured data):**
Both Prometheus (`mountpoint: /mnt/valkey-data`) and Zabbix
(`item_key: vfs.fs.size[/mnt/valkey-data,pused]`) produce the identical
candidate `/mnt/valkey-data`. Both resolve to the same component_id via
the seeded alias.

**Case (b) — Divergent-string (demonstrated on CONSTRUCTED payloads):**
No real Zabbix CPU capture exists (Phase 0: `cpu_saturation` Prometheus=3,
Zabbix=0). A constructed Zabbix CPU payload (`host: docker-host-01`) was
paired with the real captured Prometheus HighCpuUsage payload
(`instance: node-exporter:9100`). These share NO substring. Both resolved
to the same `docker-host-01` component_id via seeded aliases that bridge
the divergent identifiers.

### Phase 8 - Dependency Proximity Signal

Integrated the `DependencyProximitySignal` using a pure mathematical rule
based on graph distances. The cross-component `CartDown` alert and the
`HighDiskUsage` incident were located 3 hops apart
(`cart -> valkey -> docker-host-01 -> /mnt/valkey-data`).

With directional weighting (1.0 for inbound) and exponential decay
(`0.5^2`), the proximity score evaluated to:

- `1.0 * 0.5^2 = 0.25`

Since `0.25` is below the grouping threshold of `0.5`, **Signal 2
contributed exactly 0 groupings on this estate**. The mechanism works
correctly; the sparsity of the dependency map is the constraint.

Phase 8 complete: tests tracked, two out-of-allowlist edits
(`containment.py`, `ingestion/adapters/alertmanager.py`) reverted, CI green,
merged to `main` and tagged `phase-8`.

### Phase 8 Fix - Disk Fill Fault Robustness

Updated `estate/chaos/fill_disk.sh` to add `set -euo pipefail` so a failed
`docker exec` or `fallocate` exits non-zero rather than passing silently,
and to derive the target byte count dynamically from the filesystem's
runtime size so usage exceeds the 85% rule threshold without hitting
`ENOSPC`. `faults.jsonl` now records the bytes actually written, measured
after the fill, rather than a hardcoded request figure.

Prior to this fix, `fallocate -l 170M` failed with `ENOSPC` and the volume
filled only as a side-effect of the failed call — the script reported
success regardless.

**Estate Setup Limitation:** `estate/setup-volume.sh` must be re-run after
every `colima stop`. Without it, `/mnt/valkey-data` does not exist as a
loopback mount, the fill lands on the ~19G VM root where usage stays near
8%, and no alert fires — a silent false negative. The loop file is 200M;
ext4 overhead and reserved blocks leave ~172M usable, so fault sizing must
be derived at runtime rather than assuming 200M.

### Gate A Status and Open Investigations

**Originally verified:** one disk-fill fault produced genuine alerts from
both Prometheus (`node-exporter:9100`) and Zabbix (`docker-host-01`), with
no shared substring, bridged only by the seeded alias, producing one
incident with `source_tool_count = 2`. The stored payloads for that
incident carry full Alertmanager and Zabbix metadata (generatorURL,
fingerprint, trigger name, event time) and are not hand-posted test data.

**Currently NOT reproducible.** Re-verification on 2026-08-26 showed that
both tools detect the fault correctly:

- Prometheus `HighDiskUsage` went pending at 14:03:30Z and fired
  14:04:30Z–14:08:00Z, with the rule expression at 0.900 against a 0.85
  threshold.
- Zabbix trigger 32549 fired at 15:00:04Z (event 44, resolved by event 45
  at 15:05:04Z), the webhook reached ACE, and the alert persisted with the
  correct `component_id` (`e565f999`).

Despite this, the Zabbix alert was never joined to any incident
(`incident_id` NULL), and two Prometheus alerts from a single fault opened
two separate incidents rather than one. Root cause not yet established.

**Open investigations:**

- **(a) Ingested Zabbix alert not correlated.** The alert persists to the
  ledger with the correct component but never becomes an incident member.
  Candidate causes not yet ruled out: correlation worker started after the
  alert was published and the stream position advanced past it; or the
  alert was suppressed downstream by deduplication or flap damping.
- **(b) Single fault producing multiple incidents.** Two Prometheus alerts
  on the same component, 3m50s apart, opened separate incidents. Likely
  Alertmanager `repeat_interval` re-sends that deduplication should have
  absorbed. Would distort Phase 13 evaluation numbers if left unresolved.

Both investigations were run against a database carrying four injections'
worth of overlapping state from a single session, with workers stopped and
started between runs. A clean single-injection run is needed before
drawing conclusions.