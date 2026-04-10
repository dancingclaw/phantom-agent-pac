#!/usr/bin/env bash
# Concurrency sweet-spot finder for phantom-agent
# Usage: ./sweep_concurrency.sh [task_id] [max_concurrency] [start_from] [baseline_wall_ms]
#   task_id: task to test (default: t03, a heavy ReAct task)
#   max_concurrency: stop after this level (default: 8)
#   start_from: skip concurrency levels below this (default: 1)
#   baseline_wall_ms: pre-recorded wall time for concurrency=1 (skips running it)
#
# Runs task_id x N in parallel for N=start..max_concurrency,
# records wall time and scores, stops early if throughput drops.

set -euo pipefail
cd "$(dirname "$0")"
source .env 2>/dev/null || true

TASK="${1:-t03}"
MAX_C="${2:-8}"
START_FROM="${3:-1}"
BASELINE_MS="${4:-}"
RESULTS_FILE="benchmark-runs/sweep_$(date +%Y%m%d_%H%M%S).csv"

mkdir -p benchmark-runs
echo "concurrency,wall_ms,tasks_passed,tasks_total,throughput_tasks_per_sec,avg_per_task_ms" > "$RESULTS_FILE"

best_throughput=0
best_concurrency=1
prev_throughput=0
decline_count=0

echo "═══════════════════════════════════════════════════════"
echo " Concurrency Sweep: task=$TASK  max=$MAX_C"
echo "═══════════════════════════════════════════════════════"
echo ""

# Inject baseline if provided (skip running concurrency=1)
if [ -n "$BASELINE_MS" ] && [ "$START_FROM" -gt 1 ]; then
    throughput=$(echo "scale=4; 1 / ($BASELINE_MS / 1000)" | bc)
    echo "1,$BASELINE_MS,1,1,$throughput,$BASELINE_MS" >> "$RESULTS_FILE"
    best_throughput=$throughput
    prev_throughput=$throughput
    echo "── Concurrency 1 (pre-recorded) ────────────────────"
    echo "  Wall: ${BASELINE_MS}ms | Throughput: ${throughput} tasks/s"
    echo ""
fi

for c in $(seq "$START_FROM" "$MAX_C"); do
    echo "── Concurrency $c ──────────────────────────────────"

    # Run benchmark, capture output
    output=$(AGENT_CONCURRENCY="$c" uv run python main_v2.py "$TASK" --repeat "$c" 2>&1)

    # Extract wall time (macOS-compatible)
    wall_ms=$(echo "$output" | sed -n 's/.*Total wall time: \([0-9]*\)ms.*/\1/p')

    # Extract pass/total from SCORE line
    score_line=$(echo "$output" | sed -n 's/.*(\([0-9]*\/[0-9]* passed\)).*/\1/p')
    passed=$(echo "$score_line" | sed 's/\/.*//')
    total=$(echo "$score_line" | sed 's/.*\///' | sed 's/ .*//')

    # Calculate metrics
    throughput=$(echo "scale=4; $c / ($wall_ms / 1000)" | bc)
    avg_per_task=$(echo "scale=0; $wall_ms / $c" | bc)

    echo "  Wall: ${wall_ms}ms | Passed: ${passed}/${total} | Throughput: ${throughput} tasks/s | Avg/task: ${avg_per_task}ms"

    echo "$c,$wall_ms,$passed,$total,$throughput,$avg_per_task" >> "$RESULTS_FILE"

    # Track best
    if (( $(echo "$throughput > $best_throughput" | bc -l) )); then
        best_throughput=$throughput
        best_concurrency=$c
    fi

    # Early stop: if throughput declined 2 times in a row, stop
    if (( $(echo "$throughput < $prev_throughput" | bc -l) )); then
        decline_count=$((decline_count + 1))
    else
        decline_count=0
    fi

    if [ "$decline_count" -ge 2 ]; then
        echo ""
        echo "  ⛔ Throughput declined 2x in a row — stopping early"
        break
    fi

    # Early stop: if any task failed, note it
    if [ "$passed" != "$total" ]; then
        echo "  ⚠️  Score degradation at concurrency=$c ($passed/$total)"
    fi

    prev_throughput=$throughput
done

echo ""
echo "═══════════════════════════════════════════════════════"
echo " RESULTS: $RESULTS_FILE"
echo " SWEET SPOT: concurrency=$best_concurrency (${best_throughput} tasks/s)"
echo "═══════════════════════════════════════════════════════"
echo ""
cat "$RESULTS_FILE" | column -t -s,
