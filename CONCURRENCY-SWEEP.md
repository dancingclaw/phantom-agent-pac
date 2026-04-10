# Concurrency & Ollama Optimization — Session Log (2026-04-10)

## Current Best Configuration

```env
# .env
AGENT_CONCURRENCY=2
AGENT_DISABLE_THINKING=false   # only 9-13% speedup, keep thinking for safety
AGENT_MAX_TURNS=30
AGENT_REQUEST_TIMEOUT=300
```

**Ollama server settings** (set via `launchctl setenv` on user `david`, persist across reboots):

| Env Var | Value | Why | Gotcha |
|---------|-------|-----|--------|
| `OLLAMA_FLASH_ATTENTION` | `1` | Required for KV cache quantization | **Without this, KV_CACHE_TYPE silently falls back to f16** |
| `OLLAMA_KV_CACHE_TYPE` | `q8_0` | Halves KV cache VRAM per parallel slot | Requires flash attention to be ON |
| `OLLAMA_NUM_PARALLEL` | `4` | Server-side concurrent inference slots | Default=1 means NO parallelism regardless of agent concurrency |
| `OLLAMA_MAX_LOADED_MODELS` | `1` | All VRAM for one model | We only use qwen3.5:35b-a3b |
| `OLLAMA_GPU_OVERHEAD` | `134217728` | 128MB instead of ~20% default | Too low → macOS swaps, monitor Activity Monitor |

**Model warm-up** (must run after Ollama starts, reduces context from 262K → 8K):
```bash
curl http://localhost:11434/api/chat -d '{"model":"qwen3.5:35b-a3b","messages":[{"role":"user","content":"hi"}],"options":{"num_ctx":8192}}'
```

## Validated Sweep Results (with proper Ollama settings)

### Concurrency sweep (t41 — date calculation, light ReAct)
```
concurrency  wall_ms  throughput   avg/task   score
1            25092    0.040/s      25092ms    1/1
2            38758    0.052/s      19379ms    2/2  ← SWEET SPOT
3            61105    0.049/s      20368ms    3/3
4            130369   0.031/s      32592ms    4/4  ← collapse
```

**Sweet spot = concurrency 2.** Best throughput (0.052 tasks/s). At 3 it barely dips, at 4 it collapses.

### Thinking ON vs OFF (t41 + t10, concurrency=2)
```
                Think ON    /no_think hack   reasoning_effort=none
Task            (baseline)  (broken!)        (correct API method)
t41 (date)      43.1s       37.5s (13%)      33.2s (23% faster)
t10 (invoice)   65.1s       59.0s (9%)       60.0s (8% faster)
Total wall      65.2s       59.1s            60.0s
Score           2/2         2/2              2/2
```

**IMPORTANT: The `/no_think` text-in-system-prompt approach was broken.**
It was silently ignored by Ollama. The correct method is `reasoning_effort: "none"`
passed via the OpenAI-compatible API, which maps to `Reasoning(effort="none")`
in the OpenAI Agents SDK `ModelSettings`.

**Decision: keep thinking ON for now (AGENT_DISABLE_THINKING=false).**
The 23% speedup on reasoning tasks is tempting but previous testing with our
custom agent showed thinking is needed for harder tasks. The toggle is ready
if we want to experiment more.

## How to Enable/Disable Thinking

### Method 1: Environment variable (recommended)
```bash
# In .env:
AGENT_DISABLE_THINKING=true    # disables thinking via reasoning_effort=none
AGENT_DISABLE_THINKING=false   # keeps thinking (default)
```

### How it works internally
```
.env AGENT_DISABLE_THINKING=true
  → Config.disable_thinking = True
  → agent.py: ModelSettings(reasoning=Reasoning(effort="none"))
  → OpenAI Agents SDK sends: {"reasoning_effort": "none"} in /v1/chat/completions
  → Ollama suppresses thinking channel at inference level
```

### What does NOT work
- `/no_think` as text in system prompt — silently ignored by Ollama
- `"think": false` in extra_body on /v1/ endpoint — silently ignored (only works on native /api/chat)
- `PARAMETER think false` in Modelfile — not supported for qwen3.5 (Issue #14617)

### Native Ollama API alternative (not currently used)
If we switched from `/v1/chat/completions` to `/api/chat`, we could use:
```json
{"model": "qwen3.5:35b-a3b", "messages": [...], "think": false}
```
This is the most reliable method but would require replacing the OpenAI Agents SDK
model adapter. Not worth it for competition timeline. See `bench_ollama.py` in the
parent repo for a working example using `reasoning_effort: "none"` via /v1/.

## Critical Pitfalls Learned

### 1. OLLAMA_NUM_PARALLEL defaults to 1
Without setting this, Ollama serializes ALL requests even if you send them concurrently. Your semaphore/asyncio concurrency is meaningless — requests just queue. **This was the #1 mistake in our first sweep.**

### 2. Fast-gate tasks don't benchmark Ollama
Tasks like t04 (email_outbound without outbox) are handled by regex classifier + fast-gate — zero Ollama calls. Using these for concurrency testing only measures BitGN API latency (~7s round trip). **Use t41 or t10 for real benchmarks.**

### 3. Context window defaults to 262K
Ollama loads qwen3.5:35b-a3b with 262,144 context by default. This uses ~6GB extra VRAM for KV cache. PAC1 tasks need <4K context. Warm up with `num_ctx=8192` after model load.

### 4. Flash attention is mandatory for KV cache quantization
Setting `OLLAMA_KV_CACHE_TYPE=q8_0` without `OLLAMA_FLASH_ATTENTION=1` does nothing — Ollama silently falls back to f16. No error, no warning.

### 5. Killing Ollama on macOS requires the right user
Ollama runs under user `david` on this machine. `pkill` from user `dev` won't work. Either `sudo pkill -9 -f ollama` or log in as `david`. After kill, the port (11434) may take 3-5 seconds to release.

### 6. Don't run multiple benchmarks simultaneously
Running t03 and t41 at the same time pollutes baselines — they compete for Ollama GPU. Always ensure only one benchmark process is running when measuring.

## Time Budget Breakdown

| Component | Fast-gate tasks | Light ReAct (t41) | Heavy ReAct (t03) |
|-----------|----------------|-------------------|-------------------|
| BitGN connect + trial start | ~5s | ~5s | ~5s |
| Ollama inference | **0s** | **~20-35s** | **~130s+** |
| BitGN scoring | ~1s | ~1s | ~1s |
| **Total** | ~7s | ~25-40s | ~140s+ |
| **Ollama share** | 0% | ~85-90% | ~95% |

## VRAM Budget (M4 Max 64GB unified)

| Component | Before tuning | After tuning |
|-----------|--------------|-------------|
| Model weights (Q4_K_M) | 30GB | 30GB |
| KV cache (per slot) | ~6GB (f16, 262K ctx) | ~0.1GB (q8_0, 8K ctx) |
| System/GPU overhead | ~12GB (20%) | 0.128GB |
| **Available for parallel** | ~16GB (2-3 slots) | **~34GB (many slots)** |
| **Practical sweet spot** | 1 (serialized) | **2 (tested)** |

Note: despite having VRAM headroom for more slots, throughput peaks at 2. The bottleneck shifts to compute (attention ops) rather than memory at higher parallelism.

## Code Changes This Session

### `main_v2.py` — `--repeat N` flag
```bash
uv run python main_v2.py t04 --repeat 3   # runs t04 x3 in parallel
```

### `sweep_concurrency.sh` — automated sweep
```bash
./sweep_concurrency.sh t41 8              # sweep 1-8 with early stop
./sweep_concurrency.sh t41 8 2 25092      # skip to 2, inject baseline
```

### `agent_v2/config.py` — `disable_thinking` flag from `AGENT_DISABLE_THINKING` env var
### `agent_v2/prompts.py` — cleaned up (no longer appends `/no_think` text)
### `agent_v2/agent.py` — uses `Reasoning(effort="none")` in `ModelSettings` when flag is set

### Git state
- Repo: `dancingclaw/phantom-agent-pac` (fork of vakovalskii/phantom-agent)
- Remotes: `origin` = fork, `upstream` = original

## Research Findings (from background agent)

### Ollama optimizations investigated

| Setting | Status | Notes |
|---------|--------|-------|
| Flash attention | **Applied** | qwen3moe explicitly in FA allowlist |
| KV cache q8_0 | **Applied** | ~0.002 perplexity increase, negligible |
| NUM_PARALLEL | **Applied (4)** | Agent sweet spot is 2, but server supports 4 |
| GPU_OVERHEAD | **Applied (128MB)** | Reclaims ~12GB from default 20% reserve |
| num_ctx reduction | **Applied (8K)** | Down from 262K default |
| Disable thinking | **Tested, toggle ready** | 23% speedup (reasoning tasks) via `reasoning_effort: "none"`. `/no_think` text hack was broken. |
| MLX backend | **Not tested** | Issue #14442 reports problems with qwen3.5 35B MoE |
| q4_0 KV cache | **Not tested** | More aggressive, noticeable quality loss at higher contexts |

### Key sources
- [Ollama KV Cache Quantization](https://smcleod.net/2024/12/bringing-k/v-context-quantisation-to-ollama/)
- [Flash Attention support — Issue #13337](https://github.com/ollama/ollama/issues/13337)
- [Qwen3.5 thinking disable — Issue #14617](https://github.com/ollama/ollama/issues/14617)
- [Qwen3.5 MLX issue — Issue #14442](https://github.com/ollama/ollama/issues/14442)

## Next Steps

1. **Run full benchmark** at `AGENT_CONCURRENCY=2` — get updated score with optimized Ollama
2. **Test MLX backend** — could give up to 2x decode speed if the qwen3.5 MoE issue is fixed in Ollama 0.20
3. **Consider q4_0 KV cache** — if 2 parallel is stable, try q4_0 for more headroom (test quality first)
4. **Profile the LLM classifier** — it runs before every task and uses Ollama too. If it's slow, consider caching or using regex-only mode
