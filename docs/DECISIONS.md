# Architecture Decisions

### 2026-08-22 - Sync vs Async Database Driver
**Decision:** Use synchronous `psycopg[binary]` and synchronous SQLAlchemy 2.0.
**Alternatives Rejected:** `asyncpg` and asynchronous SQLAlchemy.
**Reason:** The core processing stages of the Alert Correlation Engine—especially deduplication, damping, text similarity processing, and graph-based correlation (NetworkX)—are heavily CPU-bound. Furthermore, as the application utilizes a dedicated worker/pipeline pattern rather than acting as a high-concurrency I/O-bound proxy, the complexity overhead of asynchronous database sessions is unwarranted. A synchronous approach simplifies database lifecycle management in `src/ace/db`, ensures compatibility with the synchronous pipeline modules (as required by the "PURE" rule), and fully satisfies our scaling targets for the demo estate without risking event-loop blocking issues.
