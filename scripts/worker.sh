#!/usr/bin/env bash

set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -z "${VIRTUAL_ENV:-}" ]]; then
    if [[ -f .venv/bin/activate ]]; then
        source .venv/bin/activate
    else
        echo "Error: Virtual environment not found at .venv"
        exit 1
    fi
fi

export PYTHONPATH="src:${PYTHONPATH:-}"
python -m ace.workers.ingest_worker
