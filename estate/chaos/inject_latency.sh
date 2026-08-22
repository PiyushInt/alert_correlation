#!/bin/bash
START=$(date -u +%Y-%m-%dT%H:%M:%SZ)
TARGET="payment"
echo "$START [CHAOS] Injecting latency on $TARGET for 60s"
docker exec -it pumba pumba netem --duration 60s delay --time 3000 re2:.*$TARGET.*
END=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "$END [CHAOS] Latency injection complete"

mkdir -p ../captures
echo "{\"fault_type\": \"inject_latency\", \"target\": \"$TARGET\", \"start_time\": \"$START\", \"end_time\": \"$END\"}" >> ../captures/faults.jsonl
