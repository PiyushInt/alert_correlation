#!/usr/bin/env bash
set -eo pipefail

echo "Starting correlation worker (Phase 7)..."
export PYTHONPATH=src
python -m ace.workers.correlation_worker
