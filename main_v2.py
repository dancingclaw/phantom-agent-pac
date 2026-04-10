"""PAC1 Benchmark Runner v2 — OpenAI Agents SDK, batch execution, realtime logs."""
from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

import asyncio
import json
import sys
import textwrap
import time
from pathlib import Path

from bitgn.harness_connect import HarnessServiceClientSync
from bitgn.harness_pb2 import (
    EndTrialRequest,
    EvalPolicy,
    GetBenchmarkRequest,
    RunState,
    StartPlaygroundRequest,
    StartRunRequest,
    StartTrialRequest,
    StatusRequest,
    SubmitRunRequest,
)
from connectrpc.errors import ConnectError

from agent_v2.config import Config
from agent_v2.agent import create_agent, run_task

CLI_RED = "\x1B[31m"
CLI_GREEN = "\x1B[32m"
CLI_BLUE = "\x1B[34m"
CLI_YELLOW = "\x1B[33m"
CLI_BOLD = "\x1B[1m"
CLI_DIM = "\x1B[2m"
CLI_CLR = "\x1B[0m"


def _render_table(rows: list[dict]) -> str:
    headers = [
        ("task_id", "Task"),
        ("score", "Score"),
        ("tool_calls", "Tools"),
        ("wall_time_ms", "Wall ms"),
    ]
    widths: dict[str, int] = {}
    for key, title in headers:
        widths[key] = max(len(title), *(len(str(r.get(key, ""))) for r in rows)) if rows else len(title)

    def fmt(row: dict | None = None) -> str:
        cells = []
        for key, title in headers:
            val = title if row is None else str(row.get(key, ""))
            cells.append(val.ljust(widths[key]) if key == "task_id" else val.rjust(widths[key]))
        return " | ".join(cells)

    sep = "-+-".join("-" * widths[k] for k, _ in headers)
    lines = [fmt(), sep]
    for row in rows:
        score = float(row.get("score", 0))
        color = CLI_GREEN if score == 1 else CLI_RED
        lines.append(f"{color}{fmt(row)}{CLI_CLR}")
    return "\n".join(lines)


def _live_summary(rows: list[dict]) -> str:
    if not rows:
        return ""
    scores = [float(r["score"]) for r in rows]
    passed = sum(1 for s in scores if s == 1.0)
    total = len(scores)
    pct = sum(scores) / total * 100
    return f"{CLI_BOLD}Progress: {passed}/{total} passed ({pct:.1f}%){CLI_CLR}"


def _save_metrics(rows: list[dict], final_score: float) -> Path:
    out = Path("benchmark-runs")
    out.mkdir(exist_ok=True)
    path = out / "v2_metrics.json"
    path.write_text(json.dumps({"final_score": final_score, "tasks": rows}, indent=2))
    return path


async def _run_single_task(
    cfg: Config,
    agent,
    harness: HarnessServiceClientSync,
    task_id: str,
    trial_id: str | None,
    benchmark_id: str,
) -> dict:
    """Run one task, fully logged."""
    print(f"\n{CLI_BLUE}{'─'*60}{CLI_CLR}")
    print(f"{CLI_BOLD}{CLI_BLUE}[{task_id}] Starting{CLI_CLR}")

    # Start trial
    if trial_id:
        trial = await asyncio.to_thread(
            harness.start_trial, StartTrialRequest(trial_id=trial_id)
        )
    else:
        trial = await asyncio.to_thread(
            harness.start_playground,
            StartPlaygroundRequest(benchmark_id=benchmark_id, task_id=task_id),
        )

    instruction = trial.instruction
    print(f"  {CLI_YELLOW}Task: {instruction}{CLI_CLR}")
    print(f"  {CLI_DIM}Runtime: {trial.harness_url[:60]}...{CLI_CLR}")

    # Run agent with hooks
    telemetry = await run_task(
        cfg, agent, trial.harness_url, instruction, task_id=task_id,
    )

    # Score
    result = await asyncio.to_thread(
        harness.end_trial, EndTrialRequest(trial_id=trial.trial_id)
    )

    score = result.score if result.score >= 0 else 0.0
    style = CLI_GREEN if score == 1 else CLI_RED
    print(
        f"\n  {style}{CLI_BOLD}[{task_id}] Score: {score:.2f}{CLI_CLR} "
        f"({telemetry.wall_time_ms}ms, {telemetry.tool_calls} tools)"
    )
    if result.score_detail:
        for line in result.score_detail:
            print(f"    {CLI_DIM}{line}{CLI_CLR}")

    return {
        "task_id": task_id,
        "score": f"{score:.2f}",
        "tool_calls": telemetry.tool_calls,
        "wall_time_ms": telemetry.wall_time_ms,
    }


async def _run_batch(
    cfg: Config,
    agent,
    harness: HarnessServiceClientSync,
    batch: list[tuple[str, str | None]],
    benchmark_id: str,
    semaphore: asyncio.Semaphore,
) -> list[dict]:
    """Run a batch of tasks with concurrency limit."""

    async def _guarded(task_id: str, trial_id: str | None) -> dict:
        async with semaphore:
            return await _run_single_task(
                cfg, agent, harness, task_id, trial_id, benchmark_id,
            )

    coros = [_guarded(tid, trial_id) for tid, trial_id in batch]
    results = await asyncio.gather(*coros, return_exceptions=True)

    rows: list[dict] = []
    for r in results:
        if isinstance(r, Exception):
            print(f"{CLI_RED}Task error: {r}{CLI_CLR}")
            rows.append({"task_id": "ERR", "score": "0.00", "tool_calls": 0, "wall_time_ms": 0})
        else:
            rows.append(r)
    return rows


async def _run_benchmark(task_filter: list[str], *, repeat: int = 1) -> None:
    cfg = Config.from_env()
    agent = create_agent(cfg)
    harness = HarnessServiceClientSync(cfg.benchmark_host)
    batch_size = cfg.concurrency

    print(f"{CLI_BOLD}PAC1 Benchmark v2 — OpenAI Agents SDK{CLI_CLR}")
    print(f"Model: {cfg.model}")
    print(f"Concurrency: {batch_size} parallel agents")
    print(f"Max turns: {cfg.max_turns}")
    print()

    print("Connecting to BitGN... ", end="", flush=True)
    status = await asyncio.to_thread(harness.status, StatusRequest())
    print(f"{CLI_GREEN}OK{CLI_CLR}")

    res = await asyncio.to_thread(
        harness.get_benchmark, GetBenchmarkRequest(benchmark_id=cfg.benchmark_id)
    )
    print(f"Benchmark: {res.benchmark_id} ({len(res.tasks)} tasks)")
    print(f"{CLI_DIM}{res.description[:200]}{CLI_CLR}")
    print()

    # Build task list with trial_ids
    trial_ids: list[str] | None = None
    run_id: str | None = None

    if task_filter:
        base = [(t.task_id, None) for t in res.tasks if t.task_id in set(task_filter)]
        tasks = base * repeat
        print(f"Playground mode: {len(base)} tasks x{repeat} = {len(tasks)} instances")
    else:
        run_response = await asyncio.to_thread(
            harness.start_run,
            StartRunRequest(
                benchmark_id=cfg.benchmark_id,
                name=cfg.run_name,
                api_key=cfg.bitgn_api_key,
            ),
        )
        run_id = run_response.run_id
        trial_ids = list(run_response.trial_ids)
        all_tasks = list(res.tasks)
        tasks = [(all_tasks[i].task_id, trial_ids[i]) for i in range(len(all_tasks))]
        print(f"Leaderboard run: {run_id} ({len(tasks)} tasks)")

    # Sliding window — all tasks launched, semaphore limits concurrency
    print(f"Sliding window: {batch_size} parallel agents")
    print(f"\n{'='*60}")

    semaphore = asyncio.Semaphore(batch_size)
    started = time.time()
    all_rows: list[dict] = []
    lock = asyncio.Lock()

    async def _guarded(task_id: str, trial_id: str | None) -> dict:
        async with semaphore:
            row = await _run_single_task(cfg, agent, harness, task_id, trial_id, cfg.benchmark_id)
            async with lock:
                all_rows.append(row)
                print(_live_summary(all_rows))
            return row

    results = await asyncio.gather(
        *[_guarded(tid, trid) for tid, trid in tasks],
        return_exceptions=True,
    )
    for r in results:
        if isinstance(r, Exception):
            print(f"{CLI_RED}Task error: {r}{CLI_CLR}")
            if r not in [row for row in all_rows]:
                all_rows.append({"task_id": "ERR", "score": "0.00", "tool_calls": 0, "wall_time_ms": 0})

    # Final summary
    wall = int((time.time() - started) * 1000)
    scores = [float(r["score"]) for r in all_rows]
    final = sum(scores) / len(scores) * 100 if scores else 0
    passed = sum(1 for s in scores if s == 1.0)

    print(f"\n\n{'='*60}")
    print(f"{CLI_BOLD}FINAL RESULTS{CLI_CLR}")
    print(f"{'='*60}")
    print(_render_table(all_rows))
    print(f"\n{CLI_BOLD}{CLI_GREEN}SCORE: {final:.2f}% ({passed}/{len(all_rows)} passed){CLI_CLR}")
    print(f"Total wall time: {wall}ms")

    if run_id is not None:
        for attempt in range(3):
            try:
                submit = await asyncio.to_thread(
                    harness.submit_run, SubmitRunRequest(run_id=run_id)
                )
                state = RunState.Name(submit.state) if isinstance(submit.state, int) else submit.state.name
                print(f"Leaderboard: {state}")
                break
            except Exception as e:
                print(f"{CLI_RED}Submit attempt {attempt+1}/3 failed: {e}{CLI_CLR}")
                if attempt < 2:
                    await asyncio.sleep(2)

    path = _save_metrics(all_rows, final)
    print(f"Metrics saved: {path}")


def main() -> None:
    args = sys.argv[1:]
    repeat = 1
    if "--repeat" in args:
        idx = args.index("--repeat")
        repeat = int(args[idx + 1])
        args = args[:idx] + args[idx + 2:]
    task_filter = args
    try:
        asyncio.run(_run_benchmark(task_filter, repeat=repeat))
    except ConnectError as exc:
        print(f"{CLI_RED}{exc.code}: {exc.message}{CLI_CLR}")
    except KeyboardInterrupt:
        print(f"\n{CLI_RED}Interrupted{CLI_CLR}")


if __name__ == "__main__":
    main()
