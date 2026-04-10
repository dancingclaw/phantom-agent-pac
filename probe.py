"""Probe benchmark tasks — dump all task IDs and instructions for pre-run analysis.

Usage:
    uv run python probe.py                    # uses BENCHMARK_ID from .env
    uv run python probe.py bitgn/pac1-comp    # override benchmark ID
    uv run python probe.py > tasks.txt        # save for analysis
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env", override=True)

import os

from bitgn.harness_connect import HarnessServiceClientSync
from bitgn.harness_pb2 import EvalPolicy, GetBenchmarkRequest, StatusRequest
from google.protobuf.json_format import MessageToDict

# Import classifier to show what skill each task would get
from agent_v2.skills.classifier import classify_task


def main() -> None:
    bench_id = sys.argv[1] if len(sys.argv) > 1 else os.getenv("BENCHMARK_ID", "bitgn/pac1-dev")
    host = os.getenv("BENCHMARK_HOST", "https://api.bitgn.com")

    print(f"Host      : {host}")
    print(f"Benchmark : {bench_id}")
    print("-" * 72)

    client = HarnessServiceClientSync(host)
    status = client.status(StatusRequest())
    print(f"Status    : OK")

    res = client.get_benchmark(GetBenchmarkRequest(benchmark_id=bench_id))
    print(f"Policy    : {EvalPolicy.Name(res.policy)}")
    print(f"Tasks     : {len(res.tasks)}")
    print("=" * 72)

    # Note: get_benchmark returns task IDs but NOT instruction text.
    # Instructions are only revealed on start_trial/start_playground.
    # So we can only see: task count, IDs, and benchmark metadata.
    for i, task in enumerate(res.tasks):
        td = MessageToDict(task, preserving_proto_field_name=True)
        task_id = td.get("task_id", f"t{i:02d}")
        instruction = td.get("instruction", "(hidden until trial start)")
        print(f"  {task_id:5s} | {instruction[:80]}")

    print("=" * 72)
    print(f"\nTotal: {len(res.tasks)} tasks")
    print(f"At ~2min/task sequential: ~{len(res.tasks) * 2}min")
    print(f"At ~2min/task concurrency=2: ~{len(res.tasks)}min")
    print()
    print("COMPETITION WORKFLOW:")
    print("  1. Run this probe to see task count + benchmark_id")
    print("  2. Update BENCHMARK_ID in .env if different")
    print("  3. Restart server: kill $(lsof -t -i :8000) && uv run python server.py &")
    print("  4. Start run: curl -X POST http://127.0.0.1:8000/api/runs -d '{}'")
    print("  5. Monitor at http://localhost:5173")
    print("  6. After first few tasks complete, check fast-gate effectiveness in logs")


if __name__ == "__main__":
    main()
