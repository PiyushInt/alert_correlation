# Alert Correlation Engine

An intelligent engine that normalizes, deduplicates, and correlates alerts from disparate monitoring tools to reduce alert noise and identify root causes.

## Development Setup

1. **Start Infrastructure (PostgreSQL 16 & Redis 7.2)**
   ```bash
   ./scripts/dev.sh
   ```

2. **Start the API Server**
   ```bash
   source .venv/bin/activate
   uvicorn ace.api.main:app --reload --port 8000
   ```

3. **Start the Ingest Worker**
   *(In a second terminal)*
   ```bash
   ./scripts/worker.sh
   ```

4. **Tests & Checks**
   ```bash
   ./scripts/check.sh
   ```
