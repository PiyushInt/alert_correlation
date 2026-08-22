#!/bin/bash
START=$(date -u +%Y-%m-%dT%H:%M:%SZ)
TARGET="checkout"
echo "$START [CHAOS] Killing service $TARGET"
docker rm -f $TARGET
sleep 60
# compose up to recover
docker compose -f ../docker-compose.yml up -d $TARGET
END=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "$END [CHAOS] Service $TARGET recovered"

mkdir -p ../captures
echo "{\"fault_type\": \"kill_service\", \"target\": \"$TARGET\", \"start_time\": \"$START\", \"end_time\": \"$END\"}" >> ../captures/faults.jsonl
