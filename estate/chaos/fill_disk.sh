#!/bin/bash
START=$(date -u +%Y-%m-%dT%H:%M:%SZ)
TARGET="/valkey-data"
echo "$START [CHAOS] Injecting disk fill on $TARGET"
fallocate -l 1G ../valkey-data/fake_full_disk.img
sleep 60
rm ../valkey-data/fake_full_disk.img
END=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "$END [CHAOS] Disk fill removed"

echo "{\"fault_type\": \"disk_fill\", \"target\": \"$TARGET\", \"start_time\": \"$START\", \"end_time\": \"$END\"}" >> ../captures/faults.jsonl
