#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CAPTURES_DIR="$SCRIPT_DIR/../captures"
mkdir -p "$CAPTURES_DIR"
set -e

QUIET_PERIOD=${1:-600} # default 10 mins

echo "Running all faults with ${QUIET_PERIOD}s quiet period between them..."

# Get absolute path to this directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

echo "=== Steady State Start ==="
date -u +%Y-%m-%dT%H:%M:%SZ
echo "Sleeping for $QUIET_PERIOD seconds..."
sleep $QUIET_PERIOD
echo "=== Steady State End ==="
date -u +%Y-%m-%dT%H:%M:%SZ

echo "1. Disk Fill"
$DIR/fill_disk.sh
sleep $QUIET_PERIOD

echo "2. CPU Saturation"
$DIR/stress_cpu.sh
sleep $QUIET_PERIOD

echo "3. Kill Service"
$DIR/kill_service.sh
sleep $QUIET_PERIOD

echo "4. Inject Latency"
$DIR/inject_latency.sh
sleep $QUIET_PERIOD

echo "5. Network Partition"
$DIR/partition.sh

echo "All faults executed."
