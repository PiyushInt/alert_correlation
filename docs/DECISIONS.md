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

### 2026-08-25 - Reachability Mechanism (Phase 8)
**Decision:** Use NetworkX for direct traversal instead of compressed bitmaps (pyroaring) for evaluating graph proximity.
**Reason:** We chose NetworkX because it is genuinely faster and more efficient for our system's lifecycle constraints. Our graph refreshes every 60 seconds (`GRAPH_REFRESH_INTERVAL`). Generating the transitive closure for bitmaps incurs a quadratic build cost on every refresh. While bitmaps are incredibly fast at query time, the heavy upfront build cost dominates the total execution time given our expected volume of proximity queries per minute. NetworkX computes paths lazily with zero build time, making it faster in total time at scale, while also saving memory and complexity.

This decision reverses if `GRAPH_REFRESH_INTERVAL` increases substantially, or if queries per interval rise significantly. If the query advantage exceeds the build cost, revisit this decision. *(Note: original timing benchmark unreproducible, script not retained).*

### 2026-08-25 - Proximity Directional Weighting (Phase 8)
**Decision:** Dependency proximity scores weight `1.0` for Outbound paths (Alert DEPENDS ON Incident) and `0.6` for Inbound paths (Incident DEPENDS ON Alert).
**Reason:** If an alert occurs on a component that depends on the incident's component (e.g., the incident is the disk filling up, and the alert is the cart failing because it depends on the disk), it represents the cascade direction, which is highly predictive of a consequence. A late-arriving alert on a dependency (the reverse) is also meaningful, as it may be the root cause finally reporting in, but it receives a lower weight to reflect its slightly lower certainty than a pure cascade.

### 2026-08-25 - Map Staleness Guard (Phase 8)
**Decision:** The Map Staleness Guard for the Dependency Proximity signal relies on a binary `edge_count == 0` check rather than a proper `MIN_MAP_COVERAGE` against the component count.
**Reason:** The PURE constraints of the correlation engine (`SignalContext`) prohibit a signal from querying the database to find the total number of known components in order to calculate true coverage. Since `SignalContext` cannot reach map health without changing the Phase 7 interface, this binary check is used as a proxy. This is a real gap, not a solved problem, and Phase 12 evaluation needs to know the guard is binary, not graded.

### 2026-08-25 - Proximity Signal Results (Phase 8)
**Decision:** The proximity signal was integrated but evaluated to 0 groupings on the demo estate.
**Reason:** 
- `cart -> /mnt/valkey-data` is 3 hops
- Score: 1.0 * (0.5)^2 = 0.25 (threshold 0.5)
- signal 2 contributed 0 groupings on this estate
- the mechanism works; the map is the constraint

### 2026-08-26 - Dynamic Disk Fill Fault Sizing (Phase 8 Fix)
**Decision:** The `disk_fill` fault injection calculates the required byte size dynamically at runtime to target 90% utilization of the `/data` volume, rather than hardcoding a fixed size (e.g., 170M).
**Reason:** The underlying `/mnt/valkey-data` volume is created as a 200MB loopback filesystem on the colima host, but ext4 overhead and reserved blocks reduce the usable space (e.g., to ~158M available). Hardcoding 170M caused `fallocate` to hit `ENOSPC` and fail silently (prior to adding strict error checking). By dynamically sizing the fill relative to the filesystem's actual `df` capacity at runtime, the script ensures a bounded, deterministic write that safely exceeds the 85% alert threshold and exits cleanly.

### 2026-08-25 - Alertmanager exported_job Candidate (Phase 4 Follow-up)
**Decision:** The `exported_job` label in Alertmanager payloads should be mapped in `AlertmanagerAdapter` during a future iteration.
**Reason:** It was discovered during Phase 8 testing that alerts originating from the Blackbox exporter carry the target application name in `exported_job` rather than `job`. Mapping this explicitly will improve component resolution for synthetic checks without relying solely on regex fallbacks.

### 2026-08-26 - Estate Limitations: Zabbix Configuration
**Decision:** The Zabbix configuration existed only inside a Docker volume with no export or seed path, making it a single point of failure for the cross-tool correlation premise since Gate A was first recorded. Note that it is now exported to `estate/zabbix/` but that no automated restore path exists yet. The `configuration.export` mechanism covers hosts, templates, and media types only. Zabbix actions are not exportable this way, so `action_7.json` is an API dump rather than an importable artifact, and the action linking trigger 32549 to mediatype 104 must be recreated manually after any reset. Note that the export has not yet been tested against a fresh zabbix-db, so its restorability is unverified.

## 2026-08-27 — The alerts table is append-only

Discovered during task 8.7: dedup.py mutated the firing alert row when a resolve
arrived, overwriting status and ends_at. No firing history survived for any
resolved Prometheus alert.

Decision: alert rows are never updated after insert, except for occurrence_count and last_seen_at,
which is dedup's specified bookkeeping under Phase 5. last_seen_at is explicitly retained as it
records the recency of duplicated alerts within the dedup window and does not represent a lifecycle
mutation. A resolution is a NEW row carrying resolves_alert_id. Incident lifecycle reads resolved rows and decides whether to
close; dedup does not perform lifecycle transitions.

Alternative rejected: keeping the mutation and adding an audit table. Rejected
because the ledger is the evidence base for every metric in Phases 12-13, and a
table that rewrites itself cannot be replayed.

Consequence: metrics computed over firing-alert counts before this date are
unreliable. Recorded in CONTEXT.md.
## 2026-08-27 — Incident resolution lifecycle
Incident auto-resolution happens in `engine.py` / `lifecycle.py` under the following conditions:
- **Full resolution**: An incident closes (`status`="resolved", `closed_at` set) if every firing `Alert` in its `incident_alerts` membership has a corresponding resolved `Alert` (matched via `resolves_alert_id`).
- **Partial resolution**: If some members resolve but others do not, the incident's `status` remains `"open"`.
- **Window expiry**: An incident auto-closes without resolution if its window has passed. This is governed by the difference between the incoming `alert.starts_at` and the `incident.opened_at` exceeding the config value `settings.CORRELATION_WINDOW`.

### 2026-08-27: Constructed Alerts in Ledger
During testing, constructed alerts were injected directly into the append-only ledger to force correlation edge cases. These alerts exist in the database from this date forward and can be identified and excluded from measurements by filtering for `source_tool = 'constructed'`.

### 2026-08-27: Component Count Reality Check (Task 8.11)

**Context:**
The build plan for Phase 4 cited a baseline of "10 divergence-table components." However, empirical analysis of the `estate/captures/` data reveals this number is fictional and was never verified against the actual tools.

**Decision:**
Seed the estate to reality, not to the document. Do not invent components to reach 10. The estate only has 3 logical components that actually receive alerts from the tools:
1. `docker-host-01` (host, emits `docker-host-01` in Zabbix, `node-exporter:9100` and `otel-collector:8889` in Prometheus)
2. `cart` (service, emits `cart:8080` in Blackbox)
3. `frontend` (service, emits `http://frontend:8080/api/cart` in Blackbox)

**Total emitted raw identifiers:** 5.
**Total logical components receiving alerts:** 3.

The original `docs/ESTATE.md` table correctly identified 3 rows (valkey, cart, vm), though its alias mapping was slightly inaccurate compared to the actual tool outputs. The estate seed data (`components.yaml`) includes 6 logical components, 3 of which are present solely for tracing/inventory topology (`/mnt/valkey-data`, `valkey`, `load-generator`) and emit no alerts.

### 2026-08-27 - Text Normalisation Rules (Phase 9)
**Decision:** Text normalisation strips UUIDs, IPv4 addresses, ISO timestamps, ports, and standalone numeric values, while explicitly PRESERVING keywords like service names (`cart`, `checkout`), error keywords (`OOMKilled`, `CrashLoopBackOff`), metric names, and environments/tenants.
**Decision 2:** We explicitly DO NOT include `alert.external_id` in the normalised string set.
**Reason:** Stripping identifiers (UUIDs, IPs, ports, times, numbers) is necessary to avoid false negatives in string comparison (e.g. two crashes at different times or different pod IPs should still match). However, over-stripping aggressively makes everything look similar, inflating signal 3's score and driving over-merging. Preserving service names and error keywords ensures the core semantic meaning remains intact for fuzzy matching. Regarding `external_id`, it typically contains random hex hashes (fingerprints) which artificially drag down the similarity `WRatio` for no semantic reason.

### 2026-08-27 - Text Similarity Signal Output (Phase 9)
**Decision:** `TextSimilaritySignal` returns the raw `WRatio` score (`raw_score / 100.0`) unconditionally, with no internal threshold gate.
**Reason:** Signals propose, containment disposes. A signal must report what it observes. Baking a threshold into the signal (e.g. gating it behind `FUZZY_MATCH_THRESHOLD`) prevents the correlation engine and the Phase 10 combination rule from seeing the actual similarity score and making an informed decision. Furthermore, `FUZZY_MATCH_THRESHOLD=85` was designed for Phase 4 component alias matching, which requires near-certainty, and is not applicable to broader alert correlation similarity.

### 2026-08-27 - Incident Text Centroid (Phase 9)
**Decision:** The text centroid for an incident is defined as the mathematical UNION of all unique normalised text tokens (extracted from labels and annotations) across all alerts in the incident. The incoming alert's normalised tokens are matched against this unified set, rather than performing pairwise comparisons against each member alert.
**Reason:** Defining the text centroid as the union of all incident text prevents the pairwise transitivity trap. A signal receiving this centroid cannot determine which member contributed which token, making it structurally impossible to erroneously chain A-B and B-C to form A-C. It also simplifies scoring to a single `fuzz.WRatio` operation against the unified string.

### 2026-08-27 - Co-occurrence Data Source (Phase 9)
**Decision:** The historical co-occurrence job (Signal 4) explicitly excludes alerts where `source_tool = 'constructed'`.
**Reason:** Signal 4 trains on historical incident groupings. Using synthetic/constructed alerts injected during testing would train the signal on fabricated groupings, producing a co-occurrence score that is entirely meaningless. The signal must measure how often real alerts fire together.
**Status on Estate:** UNMEASURED. Because the `alert_type_stats` table currently contains only 6 rows (derived from a contaminated ledger with few real faults), Signal 4 cannot produce meaningful values. It is unmeasured on this estate, not "measured at zero," which is a distinction necessary for Phase 12 evaluation.

### 2026-08-27 - Resolution Lifecycle Working on kill_service (Phase 9)
**Decision:** Recorded successful end-to-end resolution lifecycle for `kill_service` fault.
**Reason:** During Phase 9 validation, `kill_service` resulted in both Blackbox and Prometheus alerts resolving to the `cart` component, forming ONE incident with `source_tool_count = 2`, which then auto-resolved correctly (`closed_at` set). Since both tools sent `resolved` messages, this proved that the auto-resolution path functions correctly when tools actually emit resolution states, reinforcing that the missing Zabbix recoveries are a Zabbix config gap, not a pipeline defect.

### 2026-08-27 - Phase 9 Measurements & Phase 10 Implications
**Measurements:**
- `text_similarity` scored **0.525** between a Blackbox and a Prometheus alert for the same fault (`kill_service`) on the same component (`cart`). This is the observed value on this estate from a single realistic run.
- On the cart alert pair, `text_similarity` rose from **0.5806** to **0.855** after the Blackbox rule annotation was corrected from "Frontend is down (synthetic check)" to "Cart is down (synthetic check)" (open issue 11). This is the only measured instance in the project of an estate configuration change moving a signal score, and it is evidence that `text_similarity` is sensitive to alert wording rather than to fault identity — relevant to Phase 13.
- `cooccurrence` is **UNMEASURED**, not zero. The `alert_type_stats` table holds 6 rows derived from a contaminated ledger containing constructed alerts, rendering historical correlations unmeasurable on this dataset.

**Implication for Phase 10:**
With the previous combination rule of summing scores against a static 0.5 threshold, a `text_similarity` of 0.525 alone successfully merged two alerts that have NO component match and NO dependency proximity. This definitively quantified the over-merge risk and proved that summing independent signals against a low threshold was fundamentally unsafe without a more rigorous combination logic (addressed in Phase 10 by raising the threshold to 1.0 and adding weights).

### 2026-08-28 - Zabbix Recovery Events (Ingestion)
**Decision:** Zabbix adapter now parses the `status` field from incoming payloads. `PROBLEM` maps to `firing`, and `RESOLVED` maps to `resolved`. If the `status` field is completely absent (e.g., from older ledger payloads or malformed requests), it defaults to `firing` and logs a warning.
**Reason:** Zabbix actions were updated to send recovery events. Without parsing `status`, all Zabbix events were hardcoded to `firing`, meaning any incident containing a Zabbix alert would remain perpetually open, destroying MTTR measurements and leaving incidents permanently active. Parsing recovery status allows the correlation engine to correctly close incidents when all member alerts have recovered.

### 2026-08-28 - Weighted Signal Combination (Phase 10)
**Decision:** Replace the unweighted sum of signal scores with a weighted sum against a higher threshold (1.0). Signal weights are defined in `config.py` (e.g., `SIGNAL_WEIGHT_SAME_COMPONENT=1.0`, `SIGNAL_WEIGHT_DEPENDENCY_PROXIMITY=0.6`, `SIGNAL_WEIGHT_TEXT_SIMILARITY=0.5`). 
**Reason:** The principle being encoded is that `same_component` is a FACT (two alerts refer to the same thing), while the others (proximity, text similarity, cooccurrence) are CORRELATIONS. A plain sum treats them as interchangeable, leading to false merges where a single circumstantial signal (e.g., text similarity of 0.525) could merge unrelated alerts on its own because the threshold was 0.5. By weighting signals and raising the threshold to 1.0, we ensure that one deterministic signal is sufficient to merge, while circumstantial signals require corroboration (e.g. proximity + text similarity).
**Note:** The provisional weights are a reasoned starting point, not a measured result. `text_similarity` has one observation on this estate and `cooccurrence` has none. Phase 13 will tune these weights against the evaluation harness.

### 2026-08-28 - Empty Centroid Containment Refusal
**Decision:** If an incident has no resolved components (an empty centroid), it will explicitly refuse to merge any incoming alert that does have a component, returning `ContainmentResult(False, "Empty Centroid: Incident has no resolved components to calculate distance against")`.
**Reason:** An empty centroid represents an absence of evidence. It is fundamentally impossible to calculate a dependency graph distance between "nothing" and a specific component. An incident with no resolved component that blindly accretes members with components creates an un-anchored, over-merged incident, which is worse than having two separate clean incidents. The refusal itself is correct, but it now provides the correct architectural reason instead of bypassing the check or logging a false "blast radius" distance violation.

### 2026-08-28 - Blackbox Cart Rule Summary Correction
**Decision:** Changed the annotation text in the Prometheus Blackbox `CartEndpointDown` rule from "Frontend is down (synthetic check)" to "Cart is down (synthetic check)".
**Reason:** The rule probes the cart endpoint, not the frontend. The previous summary was misleading and would incorrectly inform an operator of a frontend failure when only cart was affected.
**Note:** Alerts received before 2026-08-28 carry the old "Frontend is down" text in their `raw_payload`. This is relevant to `text_similarity` scoring, as historical alert payloads will not match the corrected text exactly.

### 2026-08-28 - Distance-0 Collinearity (Phase 10 Fix)
**Decision:** `DependencyProximitySignal` now explicitly returns `0.0` for distance-0 (`best_direction == "self"`).
**Reason:** Collinearity between signals double-counts the same phenomenon. If an alert occurs on the exact same component as the incident's centroid, the `same_component` signal already scores it 1.0 (weighted to 1.0). Previously, `dependency_proximity` also hardcoded a 1.0 score for `self`, resulting in a duplicate weighted boost (0.6) for the exact same underlying fact.

### 2026-08-28 - Root Cause Candidate 'uncertain' Flag (Phase 10)
**Decision:** The `uncertain` flag on a `RootCauseCandidate` is set to `True` when there is no traversal evidence supporting the candidate's rank (i.e. `direction == "self"` or `hops == 0`).
**Reason:** The estate's topology is extremely sparse (currently 5 edges). When the graph lacks comprehensive observability edges, distance-based ranking is inherently unreliable because we cannot differentiate between "this component actually originated the failure but didn't fire an alert" and "we just don't have edges to the true root cause." Setting `uncertain = True` makes this limitation visible to operators rather than hiding behind a deceptively confident rank.

### 2026-08-28 - Root Cause Ranking as a Timing Heuristic (Phase 10)
**Decision:** With the `self` direction base score at 2.0 and the `earliest-alert` bonus at 5.0, ranking among `self`-only candidates is determined entirely by alert timing. 
**Reason:** Every incident currently in the estate is self-only, so the graph-based ranking path is implemented but unexercised on real data. It is exercised only by the synthetic-graph unit test. Phase 13 must not present ranking as validated.
