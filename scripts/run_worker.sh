#!/usr/bin/env bash
# Local dev restart loop for a Procrastinate worker.
# Usage: ./scripts/run_worker.sh scrape 2
#        ./scripts/run_worker.sh ai_decision 2
#        ./scripts/run_worker.sh "contact_fetch,email_reveal,validation" 5
set -euo pipefail

QUEUE="${1:-scrape}"
CONCURRENCY="${2:-2}"
RESTART_DELAY=5
PROCRASTINATE_POOL_MAX_SIZE="${PS_PROCRASTINATE_POOL_MAX_SIZE:-$((CONCURRENCY + 2))}"
if [ "$PROCRASTINATE_POOL_MAX_SIZE" -lt 4 ]; then
    PROCRASTINATE_POOL_MAX_SIZE=4
fi

echo "Starting worker: queue=$QUEUE concurrency=$CONCURRENCY pool_max=$PROCRASTINATE_POOL_MAX_SIZE"

while true; do
    PS_WORKER_PROCESS=1 PS_WORKER_CONCURRENCY="$CONCURRENCY" PS_PROCRASTINATE_POOL_MAX_SIZE="$PROCRASTINATE_POOL_MAX_SIZE" uv run python -m procrastinate \
        --app=app.queue.app worker \
        -q "$QUEUE" \
        -c "$CONCURRENCY" || true
    echo "Worker exited. Restarting in ${RESTART_DELAY}s... (Ctrl-C to stop)"
    sleep "$RESTART_DELAY"
done
