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
