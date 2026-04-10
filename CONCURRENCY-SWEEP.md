# Concurrency Sweep — Session State (2026-04-10)

## What We're Doing

Finding the optimal `AGENT_CONCURRENCY` for the full PAC1 benchmark on local Ollama (qwen3.5:35b-a3b, M4 Max 64GB).

## What We Learned

### Previous sweep was invalid
- Ran t04 (a fast-gate task) at concurrency 1-6 — but t04 **never calls Ollama** (regex classifier short-circuits it). We were benchmarking BitGN API latency, not GPU.
- Also, `OLLAMA_NUM_PARALLEL` was at default (1), so Ollama serialized all requests regardless of our semaphore. True parallel inference was never happening.

### Time breakdown for real tasks
- **Fast-gate tasks** (t04, t07, t08, t09, t33, etc.): ~7s, all BitGN API overhead, zero Ollama
- **Heavy ReAct tasks** (t03 capture+distill): ~140s+, ~95% Ollama inference
- **Light ReAct tasks** (t41 date calc): ~60-90s, ~90% Ollama inference
- Raw Ollama latency for 20 tokens: 31.6s (mostly thinking tokens)

## Ollama Optimization — Applied Before Reboot

Set via `launchctl setenv` on user `david`:

| Env Var | Value | Why |
|---------|-------|-----|
| `OLLAMA_FLASH_ATTENTION` | `1` | Required for KV cache quantization to work (without this, KV_CACHE_TYPE silently falls back to f16) |
| `OLLAMA_KV_CACHE_TYPE` | `q8_0` | Halves KV cache VRAM per parallel slot. Negligible quality loss. |
| `OLLAMA_NUM_PARALLEL` | `4` | Server-side concurrent inference slots. Was 1 (default) = no parallelism. |
| `OLLAMA_MAX_LOADED_MODELS` | `1` | All VRAM for one model, no room reserved for phantom models |
| `OLLAMA_GPU_OVERHEAD` | `134217728` | 128MB instead of default ~20%. Reclaims VRAM for KV cache. |

## What To Do After Reboot

### 1. Verify Ollama settings
```bash
ollama ps
# Should show qwen3.5:35b-a3b loaded
# Check that parallel slots are active
```

### 2. Warm up model with reduced context
```bash
curl http://localhost:11434/api/chat -d '{"model":"qwen3.5:35b-a3b","messages":[{"role":"user","content":"hi"}],"options":{"num_ctx":8192}}'
```
Context was 262144 (256K!) — way too large. 8192 is plenty for PAC1 tasks (<4K actual usage).

### 3. Run the sweep
```bash
cd /Users/dev/Projects/challenges/bitgn-pac/phantom-agent
./sweep_concurrency.sh t41 8
```
This runs task t41 (date calculation, light ReAct, uses Ollama) at concurrency 1 through 8, with early stop if throughput drops twice. Results go to `benchmark-runs/sweep_*.csv`.

If you have a baseline wall_ms from concurrency=1, skip it:
```bash
./sweep_concurrency.sh t41 8 2 <baseline_wall_ms>
```

### 4. Run full benchmark at sweet spot
```bash
AGENT_CONCURRENCY=<sweet_spot> uv run python main_v2.py
```

## Code Changes Made This Session

### `main_v2.py` — added `--repeat` flag
Allows running same task N times in parallel for benchmarking:
```bash
uv run python main_v2.py t04 --repeat 3   # runs t04 x3 in parallel
```

### `sweep_concurrency.sh` — new file
Automated concurrency sweep script with early stop and CSV output.

### Git state
- `phantom-agent/` committed and pushed to `dancingclaw/phantom-agent-pac` (fork)
- Remotes: `origin` = your fork, `upstream` = vakovalskii/phantom-agent
- The `--repeat` and sweep changes are NOT yet committed

## Other Ideas Not Yet Implemented

- **Disable thinking tokens** for classifier/fast-gate calls (`"think": false` in API body or `/no_think` suffix). Could save 50-80% latency on simple routing.
- **num_ctx via API**: pass `"options": {"num_ctx": 8192}` in Ollama requests instead of using the 256K default.
- **More fast-gates**: identify additional tasks with deterministic answers to skip Ollama entirely.
