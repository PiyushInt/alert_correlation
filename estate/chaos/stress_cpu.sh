#!/bin/bash
START=$(date -u +%Y-%m-%dT%H:%M:%SZ)
TARGET="frontend"
echo "$START [CHAOS] Injecting CPU saturation on $TARGET for 60s"
docker run --rm -it jess/stress --cpu 2 --timeout 60
END=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "$END [CHAOS] CPU saturation complete"

echo "{\"fault_type\": \"cpu_saturation\", \"target\": \"$TARGET\", \"start_time\": \"$START\", \"end_time\": \"$END\"}" >> ../captures/faults.jsonl
