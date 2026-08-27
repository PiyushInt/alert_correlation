#!/usr/bin/env bash
# Inject a disk-fill fault and print the resulting pipeline state.
set -euo pipefail
DUR="${1:-300}"
PSQL="PGPASSWORD=ace_password psql -h localhost -p 5433 -U ace_user -d ace_db -P pager=off"

echo "=== restarting workers ==="
pkill -f "python -m ace.workers" || true
sleep 1
uv run python -m ace.workers.ingest_worker &
uv run python -m ace.workers.correlation_worker &
sleep 2

echo "=== snapshot ==="
bash scripts/db_snapshot.sh

echo "=== before ==="
eval "$PSQL -c 'SELECT count(*) AS alerts FROM alerts;' \
           -c 'SELECT count(*) AS incidents FROM incidents;'"

echo "=== injecting (${DUR}s) ==="
bash estate/chaos/kill_service.sh "$DUR"
echo "waiting for detection..."
sleep 180

echo "=== alerts ==="
eval "$PSQL -c 'SELECT a.source_tool, a.status, c.canonical_name, a.received_at
               FROM alerts a LEFT JOIN components c ON c.id = a.component_id
               ORDER BY a.received_at DESC LIMIT 8;'"

echo "=== incidents ==="
eval "$PSQL -c 'SELECT id, status, source_tool_count, alert_count, closed_at
               FROM incidents ORDER BY opened_at DESC LIMIT 3;'"

echo "=== join reasons ==="
eval "$PSQL -c 'SELECT incident_id, join_reason, join_score
               FROM incident_alerts ORDER BY joined_at DESC LIMIT 8;'"

echo "=== per-signal scores ==="
eval "$PSQL -c 'SELECT incident_id, join_score, signal_scores FROM incident_alerts WHERE signal_scores IS NOT NULL ORDER BY joined_at DESC LIMIT 3;'"
