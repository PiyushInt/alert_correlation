#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CAPTURES_DIR="$SCRIPT_DIR/../captures"
mkdir -p "$CAPTURES_DIR"

# Minimum duration is 300s. The Prometheus scrape interval is 15s, 
# the rule 'for' duration is 1m, and Alertmanager group_wait adds more time.
# Zabbix also polls on a 30s schedule, so 300s ensures the full pipeline has time to fire.
DURATION=${1:-300}
START=$(date -u +%Y-%m-%dT%H:%M:%SZ)
TARGET="/mnt/valkey-data"
FAULT_ID="disk_fill_$(date +%s)"

# 5. FAULT RECORD (start)
echo "{\"fault_id\": \"$FAULT_ID\", \"fault_type\": \"disk_fill\", \"target\": \"$TARGET\", \"container\": \"estate-valkey-1\", \"start_time\": \"$START\", \"end_time\": null, \"size\": \"170M\"}" >> "$CAPTURES_DIR/faults.jsonl"

# 6. Corrected log line
echo "$START [CHAOS] Injecting disk fill on $TARGET for ${DURATION}s"
docker exec estate-valkey-1 fallocate -l 170M /data/fill.img

# 4. CLEANUP TRAP
cleanup() {
    END=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    echo "$END [CHAOS] Removing disk fill..."
    docker exec estate-valkey-1 rm -f /data/fill.img
    
    # 5. FAULT RECORD (end) - rewrite the line with the end_time using python
    python3 -c "
import json, sys
lines = []
with open('$CAPTURES_DIR/faults.jsonl', 'r') as f:
    for line in f:
        d = json.loads(line)
        if d.get('fault_id') == '$FAULT_ID' and d.get('end_time') is None:
            d['end_time'] = '$END'
        lines.append(json.dumps(d))
with open('$CAPTURES_DIR/faults.jsonl', 'w') as f:
    f.write('\n'.join(lines) + '\n')
"
    
    echo "$END [CHAOS] Disk fill removed"
}

trap cleanup EXIT INT

# 3. PROGRESS OUTPUT
elapsed=0
while [ $elapsed -lt $DURATION ]; do
    sleep 30
    elapsed=$((elapsed + 30))
    echo "[$elapsed/$DURATION s] Current usage on /data:"
    docker exec estate-valkey-1 df -h /data | tail -n 1
done
