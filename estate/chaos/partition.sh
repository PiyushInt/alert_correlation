#!/bin/bash
START=$(date -u +%Y-%m-%dT%H:%M:%SZ)
TARGET="frontend"
echo "$START [CHAOS] Injecting network partition on $TARGET for 60s"
docker exec -it pumba pumba netem --duration 60s loss --percent 100 re2:.*$TARGET.*
END=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "$END [CHAOS] Network partition complete"

mkdir -p ../captures
echo "{\"fault_type\": \"partition\", \"target\": \"$TARGET\", \"start_time\": \"$START\", \"end_time\": \"$END\"}" >> ../captures/faults.jsonl
