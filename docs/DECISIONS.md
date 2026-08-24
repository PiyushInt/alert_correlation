# Architecture Decisions

### 2026-08-22 - Sync vs Async Database Driver
**Decision:** Use synchronous `psycopg[binary]` and synchronous SQLAlchemy 2.0.
**Alternatives Rejected:** `asyncpg` and asynchronous SQLAlchemy.
**Reason:** The core processing stages of the Alert Correlation Engine—especially deduplication, damping, text similarity processing, and graph-based correlation (NetworkX)—are heavily CPU-bound. Furthermore, as the application utilizes a dedicated worker/pipeline pattern rather than acting as a high-concurrency I/O-bound proxy, the complexity overhead of asynchronous database sessions is unwarranted. A synchronous approach simplifies database lifecycle management in `src/ace/db`, ensures compatibility with the synchronous pipeline modules (as required by the "PURE" rule), and fully satisfies our scaling targets for the demo estate without risking event-loop blocking issues.

### 2026-08-22 - ENUM Strategy
**Decision:** Use plain string columns validated by Python `Enum`s instead of native PostgreSQL `ENUM` types.
**Alternatives Rejected:** Native PostgreSQL `ENUM`s, Check Constraints mapping integer states.
**Reason:** Native PostgreSQL `ENUM` types are notoriously difficult to alter (e.g. removing a value) without dropping and recreating the type, which requires locking tables in production. Using Python enums combined with string columns provides flexibility for schema evolution while still enforcing strict type safety at the application layer. (We will also back string columns with `CHECK` constraints if needed to enforce data consistency strictly at the database level).
### 2026-08-22 - Severity Mapping
**Decision:** Use an ordered integer scale for severity mapping. critical=5, high=4, medium=3, low=2, info=1.
**Alternatives Rejected:** Unordered strings.
**Reason:** Using an ordered integer scale allows >= comparisons to work naturally. This is critical for bypass thresholds (e.g., severity >= CRITICAL) and for Zabbix mapping in Phase 4. Prometheus "critical" and "page" map to 5, "warning" maps to 3, and unknown values default to 3 (with a logged WARNING). "page" is explicitly added because Prometheus uses it to mean "wake someone up", which aligns with critical.

### 2026-08-22 - Lag Measurement (Phase 3)
**Decision:** Defer pipeline lag measurement until the consumer group is implemented in Phase 5. In Phase 3, the health evaluator checks if the consumer group exists on the stream. If it does not, it returns "lag unknown" and does not contribute to the bypass state decision.
**Alternatives Rejected:** Measuring the age of the oldest entry in the stream directly.
**Reason:** Measuring the oldest entry in the stream when no consumer exists means the oldest entry will age forever, tripping the BYPASS state and never clearing. True lag is the age of the oldest *unread* entry, which requires consumer group tracking.

### 2026-08-22 - Zabbix Severity Mapping (Phase 4)
**Decision:** Map Zabbix severities into our ordered scale as follows: Not classified -> info(1), Information -> info(1), Warning -> low(2), Average -> medium(3), High -> high(4), Disaster -> critical(5). Unknown values default to 3 with a logged WARNING.
**Alternatives Rejected:** Dropping unknown severities or mapping High to critical.
**Reason:** Matches the ordered 1-5 scale. Zabbix's 6-level scale collapses into 5 by merging Not classified and Information. Zabbix disk trigger emits High, which correctly maps to high(4).

### 2026-08-22 - Cross-Tool Identity & CMDB Seeding (Phase 4)
**Decision:** Cross-tool identity for disparate infrastructure components (e.g., node-exporter:9100 vs docker-host-01) requires seeded knowledge via a YAML file simulating a CMDB. 
**Alternatives Rejected:** Discovering it automatically via string algorithms by lowering `FUZZY_MATCH_THRESHOLD`.
**Reason:** Lowering `FUZZY_MATCH_THRESHOLD` silently merges unrelated components. Real-world disparate systems require external knowledge (CMDB) to bridge divergent hostnames/identifiers.

### 2026-08-22 - Component Resolution Precedence (Phase 4)
**Decision:** Resolution iterates over extracted identifier candidates (ordered from most-specific to least-specific). Pass 1: first exact or alias match wins. Pass 2: first fuzzy match wins. A fuzzy match NEVER beats an exact/alias match from a lower-precedence candidate.
**Alternatives Rejected:** Allowing fuzzy matches to preempt exact matches from lower-priority candidates.
**Reason:** Explicit matches (exact/manual aliases) are high-confidence signals and must override fuzzy (string-similarity) matches, which are error-prone and used only as a last resort.

### 2026-08-22 - Pipeline Order (Phase 5)
**Decision:** Damping runs BEFORE Deduplication.
**Alternatives Rejected:** Dedup before damping.
**Reason:** If dedup runs first, it collapses rapid `firing` -> `resolved` -> `firing` transitions into a single deduped entry before damping can count the flips. Damping must see every state transition.

### 2026-08-22 - Flap Counting (Phase 5)
**Decision:** Use a sliding window via Redis Sorted Sets (`ZADD` with timestamp, `ZREMRANGEBYSCORE`, `ZCARD`) to count flips within `FLAP_WINDOW`.
**Alternatives Rejected:** A running total that only resets after a quiet period.
**Reason:** A running total would accumulate unrelated flips over hours (e.g., 4 flips, hour silence, 2 flips = 6 flips) and incorrectly trigger thresholds.

### 2026-08-22 - Stream Cap (Phase 5)
**Decision:** `alerts.raw` and `alerts.clean` capped at ~10,000 entries using `XADD ... MAXLEN ~`.
**Alternatives Rejected:** Uncapped streams or very tight caps.
**Reason:** At a peak burst of 1 alert/minute (1,440/day), 10,000 entries retains ~7 days of events. This is generous for the demo estate and ensures memory safety, while allowing plenty of time since nothing consumes `alerts.clean` until Phase 7.

### 2026-08-22 - Resolved Alerts in Deduplication (Phase 5)
**Decision:** Dedup keys on `{fingerprint}` (excluding status). A resolved alert triggers a dedup hit for its original firing alert, updating the original's status to `resolved` and setting its `ends_at`. The dedup key is then deleted to avoid the re-fire bug. The incoming resolved alert is forwarded to `alerts.clean` and linked via `resolves_alert_id`.
**Alternatives Rejected:** Keying on `{fingerprint}:{status}`.
**Reason:** Separating keys leaves the original firing row "open" in the database indefinitely. By mapping `resolved` to the original `firing` dedup key, we properly close the canonical event. Deleting the key immediately after allows subsequent new occurrences of the same alert to correctly open a new row.

### 2026-08-22 - Immutable Ledger and Counting Definitions (Phase 5)
**Decision:** The `alerts` table acts as an immutable ledger of every payload received. Deduplication controls downstream flow (to `alerts.clean`) and updates aggregate state (`occurrence_count`, `last_seen_at`) on the first-seen row, but it DOES NOT delete duplicate rows from the database.
**Alternatives Rejected:** Deleting duplicate rows to save database storage space.
**Reason:** Deleting duplicates destroys the raw event history necessary for Phase 12's replay harness and corrupts baseline metrics which rely on the total number of received alerts. 
**Counting Definitions:**
- **RECEIVED alerts:** `count(*)` from `alerts`. This is the denominator for Phase 0 baselines (e.g., 35% unresolved rate, 47.5% duplicate rate).
- **DISTINCT alerts:** `count(DISTINCT fingerprint)`, which is equivalent to the number of rows forwarded to `alerts.clean`.

### 2026-08-24 - Dependency Map Edges (Phase 6)
**Decision:** Datastore edges, host/volume edges, and unobservable service edges are seeded from the inventory `topology.yaml` rather than extracted from traces. 
**Alternatives Rejected:** Relying purely on observed trace traffic for the dependency map.
**Reason:** The OpenTelemetry demo estate has severe limitations in emitting client spans:
- The OTel Demo's frontend does not emit client spans for its backend calls in this configuration, so service-to-service edges below the entry point are invisible to trace extraction.
- Datastore calls from cart emit no spans at all.
- Trace extraction therefore observed only the edges it could: `load-generator -> frontend`.
- Everything on the headline chain is inventory-seeded.

The core of the project was described as being "built from observed traffic", but on this estate, all 4 edges on the headline critical path are hand-seeded:
- `frontend -> cart`: inventory (seeded)
- `cart -> valkey`: inventory (seeded)
- `valkey -> docker-host-01`: inventory (seeded)
- `docker-host-01 -> /mnt/valkey-data`: inventory (seeded)

### Standing Rule - No Silent Failures (Phase 6 onwards)
**Decision:** Components whose output nothing downstream validates must fail LOUDLY.
**Reason:** Phase 6's extractor dropped resolution misses silently and swallowed DB insert errors (a missing first_seen), so a completely non-functional dependency map was indistinguishable from a working one until an edge count was requested. Every drop, skip, or swallowed error must be logged at WARNING and counted in a metric.

Furthermore, instrumentation that is never exposed is the same class of defect as an error that is never logged. Counters and metrics MUST be observable (e.g. via an exposed `/metrics` endpoint) the moment they are introduced.

### 2026-08-24 - Correlation Centroid Definition (Phase 7)
**Decision:** The "centroid" for the `same_component` signal is defined as the *set of unique component IDs* from all alerts currently in the incident. An alert scores 1.0 if its component ID is in this set.
**Reason:** The "CENTROID, NOT ANY-MEMBER" containment rule requires that an alert scores against the incident *as a whole*. This definition generalizes well: for future signals (e.g., proximity), distance must be measured from the incident's entire component set, rather than by walking pairwise edges from single members (which reintroduces transitivity).

### 2026-08-24 - No Transitive Closure Rule (Phase 7)
**Decision:** Grouping is NEVER connected-components over a pairwise similarity graph. Transitivity is structurally prevented (Option A) by the `IncidentCentroid` abstraction. The engine passes an `IncidentCentroid` to signals, not the member alert list.
**Reason:** If a signal is physically deprived of the member alert list, it cannot iterate members to compute `max(pairwise)`. This enforcement mechanism makes it structurally impossible to write a transitivity bug in Phase 8 (Proximity) or Phase 9 (TextSimilarity), as the signal author is forced to evaluate against the centroid representation.

### 2026-08-24 - NULL Component IDs (Phase 7)
**Decision:** Alerts with `component_id=None` score 0.0 for `same_component` matches against other `NULL` components.
**Reason:** `NULL != NULL`. Two unresolved alerts from different unknown components are not the same component. They will open separate incidents unless grouped by another signal (like text similarity).
