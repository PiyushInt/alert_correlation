# Architecture Decisions

### 2026-08-22 - Sync vs Async Database Driver
**Decision:** Use synchronous `psycopg[binary]` and synchronous SQLAlchemy 2.0.
**Alternatives Rejected:** `asyncpg` and asynchronous SQLAlchemy.
**Reason:** The core processing stages of the Alert Correlation Engine—especially deduplication, damping, text similarity processing, and graph-based correlation (NetworkX)—are heavily CPU-bound. Furthermore, as the application utilizes a dedicated worker/pipeline pattern rather than acting as a high-concurrency I/O-bound proxy, the complexity overhead of asynchronous database sessions is unwarranted. A synchronous approach simplifies database lifecycle management in `src/ace/db`, ensures compatibility with the synchronous pipeline modules (as required by the "PURE" rule), and fully satisfies our scaling targets for the demo estate without risking event-loop blocking issues.

### 2026-08-22 - ENUM Strategy
**Decision:** Use plain string columns validated by Python `Enum`s instead of native PostgreSQL `ENUM` types.
**Alternatives Rejected:** Native PostgreSQL `ENUM`s, Check Constraints mapping integer states.
**Reason:** Native PostgreSQL `ENUM` types are notoriously difficult to alter (e.g. removing a value) without dropping and recreating the type, which requires locking tables in production. Using Python enums combined with string columns provides flexibility for schema evolution while still enforcing strict type safety at the application layer. (We will also back string columns with `CHECK` constraints if needed to enforce data consistency strictly at the database level).
