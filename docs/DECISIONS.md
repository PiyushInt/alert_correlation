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
