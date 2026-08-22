#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CAPTURES_DIR="$SCRIPT_DIR/../captures"
mkdir -p "$CAPTURES_DIR"

DURATION=${1:-300}
START=$(date -u +%Y-%m-%dT%H:%M:%SZ)
TARGET="cart"
FAULT_ID="inject_latency_$(date +%s)"

echo "{\"fault_id\": \"$FAULT_ID\", \"fault_type\": \"inject_latency\", \"target\": \"$TARGET\", \"container\": \"estate-$TARGET-1\", \"start_time\": \"$START\", \"end_time\": null}" >> "$CAPTURES_DIR/faults.jsonl"

echo "$START [CHAOS] Injecting latency on $TARGET for ${DURATION}s"

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
    
    echo "$END [CHAOS] Latency injection complete"
}

trap cleanup EXIT INT

# We use one-shot pumba container to inject latency
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock gaiaadm/pumba:0.9.0 netem --tc-image gaiadocker/iproute2 --duration ${DURATION}s delay --time 3000 "re2:.*$TARGET.*"
