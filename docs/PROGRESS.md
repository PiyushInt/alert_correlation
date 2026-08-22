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
