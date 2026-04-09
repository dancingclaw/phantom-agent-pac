# Configuration and Launch

## Environment Variables

### Required

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | Provider API key |
| `OPENAI_BASE_URL` | OpenAI-compatible API URL (if not OpenAI) |
| `MODEL_ID` | Model name (default: `gpt-4.1-2025-04-14`) |

### For Leaderboard

| Variable | Description |
|---|---|
| `BITGN_API_KEY` | BitGN leaderboard key |
| `BITGN_RUN_NAME` | Run name on leaderboard |

### Agent Settings

| Variable | Default | Description |
|---|---|---|
| `AGENT_MAX_STEPS` | 30 | Max ReAct loop steps per task |
| `AGENT_MAX_TOKENS` | 4096 | Max tokens per LLM response |
| `AGENT_REQUEST_TIMEOUT_SECONDS` | 60 | LLM request timeout |
| `AGENT_JSON_REPAIR_RETRIES` | 2 | Attempts to fix invalid JSON |
| `AGENT_FASTPATH_MODE` | framed | `off` / `framed` / `all` |
| `AGENT_USE_GBNF` | auto | GBNF grammar (for local models) |
| `BENCHMARK_HOST` | https://api.bitgn.com | BitGN harness URL |
| `BENCHMARK_ID` | bitgn/pac1-dev | Benchmark ID |
| `PCM_RETRY_ATTEMPTS` | 4 | Retries on transient runtime errors |

## Launch Commands

```bash
cd pac1-py

# Install dependencies
make sync

# Full leaderboard run
OPENAI_API_KEY=... OPENAI_BASE_URL=... MODEL_ID=... BITGN_API_KEY=... make run

# Test run (playground, no leaderboard)
uv run python main.py t01 t03 t42

# Run with maximum LLM usage
AGENT_FASTPATH_MODE=off uv run python main.py

# Run a specific task for debugging
AGENT_FASTPATH_MODE=off uv run python main.py t42
```

## Artifacts

After a run, saved in `benchmark-runs/`:
- `latest_metrics.json` — full metrics (totals + per-task)
- `latest_metrics.csv` — CSV export
- `latest_full_run.txt` — full log (only for full runs)
