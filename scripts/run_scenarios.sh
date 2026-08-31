#!/bin/bash
set -e
export DATABASE_URL="postgresql+psycopg://ace_user:ace_password@localhost:5433/ace_db_eval"
source .venv/bin/activate

# We do not set DEDUP_WINDOW here inside the script because the value must match 
# exactly what the running stack was started with. The script cannot change that 
# configuration after the fact, so we explicitly verify the environment matches.
#
# NOTE on Issue 17: DEDUP_WINDOW=330 exceeds CORRELATION_WINDOW=300 and therefore 
# triggers the dead zone bug where resolutions arriving between 300-330s lose their 
# dedup link (cache expired) and fail to find the original incident (window closed). 
# The evaluation runs with this known defect active. Phase 13 must state that.
if [ "$DEDUP_WINDOW" != "330" ]; then
    echo "ERROR: DEDUP_WINDOW must be explicitly exported as 330 before running this script."
    echo "This ensures the isolation gaps calculated by this script match the stack."
    exit 1
fi

echo "Waiting 340s for any remaining incidents from previous chaotic runs to exit dedup window..."
sleep 340

for scenario in cascade/disk_fill cascade/cart_kill offgraph/noisy_neighbour adversarial/unrelated_concurrent; do
    echo "=== Running $scenario ==="
    python eval/runner.py --scenario eval/scenarios/$scenario.yaml --replay | tee logs/out_$(basename $scenario).log
    echo "=== Finished $scenario. Waiting 30s to ensure DEDUP_WINDOW completes... ==="
    sleep 30
done
