#!/usr/bin/env bash
set -euo pipefail
ts=$(date +%Y%m%d-%H%M%S)
PGPASSWORD=ace_password pg_dump -h localhost -p 5433 -U ace_user -d ace_db \
  -F c -f "backups/ace_db-${ts}.dump"
echo "backups/ace_db-${ts}.dump"
