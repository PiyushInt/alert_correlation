#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CAPTURES_DIR="$SCRIPT_DIR/../captures"
mkdir -p "$CAPTURES_DIR"

DURATION=${1:-300}
START=$(date -u +%Y-%m-%dT%H:%M:%SZ)
TARGET="vm"
FAULT_ID="cpu_saturation_$(date +%s)"

echo "{\"fault_id\": \"$FAULT_ID\", \"fault_type\": \"cpu_saturation\", \"target\": \"$TARGET\", \"container\": \"jess/stress\", \"start_time\": \"$START\", \"end_time\": null}" >> "$CAPTURES_DIR/faults.jsonl"

echo "$START [CHAOS] Injecting CPU saturation on $TARGET for ${DURATION}s"

cleanup() {
    END=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    
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
    
    echo "$END [CHAOS] CPU saturation complete"
}

trap cleanup EXIT INT

docker run --rm jess/stress --cpu 4 --timeout $DURATION
