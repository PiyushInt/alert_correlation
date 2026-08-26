#!/bin/bash
set -euo pipefail

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

# Calculate bytes needed to reach 90% disk utilization
DF_OUTPUT=$(docker exec estate-valkey-1 df -B1 /data | tail -n 1)
SIZE=$(echo "$DF_OUTPUT" | awk '{print $2}')
USED=$(echo "$DF_OUTPUT" | awk '{print $3}')
AVAIL=$(echo "$DF_OUTPUT" | awk '{print $4}')

TARGET_USED=$(( SIZE * 90 / 100 ))
FILL_BYTES=$(( TARGET_USED - USED ))

if [ "$FILL_BYTES" -le 0 ]; then
    echo "Error: Disk is already >= 90% full."
    exit 1
fi
if [ "$FILL_BYTES" -gt "$AVAIL" ]; then
    echo "Error: Cannot reach 90% usage (need $FILL_BYTES bytes, but only $AVAIL available)."
    exit 1
fi

echo "$START [CHAOS] Injecting disk fill on $TARGET for ${DURATION}s (target: ${FILL_BYTES} bytes)"
docker exec estate-valkey-1 fallocate -l "${FILL_BYTES}" /data/fill.img
docker exec estate-valkey-1 sync

# Measure actual bytes written
ACTUAL_BYTES=$(docker exec estate-valkey-1 stat -c%s /data/fill.img)

# 5. FAULT RECORD (start)
echo "{\"fault_id\": \"$FAULT_ID\", \"fault_type\": \"disk_fill\", \"target\": \"$TARGET\", \"container\": \"estate-valkey-1\", \"start_time\": \"$START\", \"end_time\": null, \"size\": \"${ACTUAL_BYTES}B\"}" >> "$CAPTURES_DIR/faults.jsonl"

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
