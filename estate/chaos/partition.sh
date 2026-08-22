#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CAPTURES_DIR="$SCRIPT_DIR/../captures"
mkdir -p "$CAPTURES_DIR"

DURATION=${1:-300}
START=$(date -u +%Y-%m-%dT%H:%M:%SZ)
TARGET="cart"
FAULT_ID="partition_$(date +%s)"

echo "{\"fault_id\": \"$FAULT_ID\", \"fault_type\": \"partition\", \"target\": \"$TARGET\", \"container\": \"estate-$TARGET-1\", \"start_time\": \"$START\", \"end_time\": null}" >> "$CAPTURES_DIR/faults.jsonl"

echo "$START [CHAOS] Injecting network partition on $TARGET for ${DURATION}s"

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
    
    docker network connect estate_default estate-cart-1
    echo "$END [CHAOS] Network partition complete"
}

trap cleanup EXIT INT

# We disconnect cart from the docker network
docker network disconnect estate_default estate-cart-1
sleep ${DURATION}
