# PAC1 Benchmark Agent

## Quick Start

```bash
cd pac1-py
uv sync

# Start dashboard (backend + frontend)
OPENAI_API_KEY=<key> OPENAI_BASE_URL=<url> MODEL_ID=gpt-oss-120b \
BITGN_API_KEY=<bgn-key> AGENT_CONCURRENCY=20 \
uv run python server.py
# Then: cd dashboard && npm run dev

# CLI run (no dashboard)
OPENAI_API_KEY=<key> OPENAI_BASE_URL=<url> MODEL_ID=gpt-oss-120b \
uv run python main_v2.py
```

Dashboard: http://localhost:5173 | API: http://localhost:8000

## Architecture

**v2 Agent** — Pure LLM ReAct on OpenAI Agents SDK. No hardcoded workflows.

```
User task → LLM Classifier (picks skill) → Agent(system_prompt + skill_prompt + task)
  → ReAct loop: LLM → tool call → result → LLM → ... → report_completion
```

### Key Files

| File | Purpose |
|---|---|
| `main_v2.py` | CLI benchmark runner (sliding window parallelism) |
| `server.py` | FastAPI + SSE backend for dashboard |
| `agent_v2/agent.py` | Agent creation, run_task with fallback |
| `agent_v2/prompts.py` | XML system prompt (<MAIN_ROLE>, <SECURITY>, <CONSTRAINTS>...) |
| `agent_v2/tools.py` | 11 tools via @function_tool |
| `agent_v2/skills/` | 12 skill prompts (.md) + classifier + LLM classifier |
| `agent_v2/hooks.py` | Live logging hooks (console + SSE) |
| `agent_v2/runtime.py` | Async PCM gRPC wrapper |
| `agent_v2/db.py` | SQLite persistence (runs, tasks, events) |
| `agent_v2/config.py` | Env config (model, concurrency, max_turns) |

### Skills (12)

| Skill | When |
|---|---|
| security_denial | Prompt injection, hostile payloads |
| inbox_processing | Process CRM/knowledge inbox messages |
| email_outbound | Send email via /outbox/ |
| crm_lookup | Find accounts, contacts, emails, managers |
| invoice_creation | Create invoice JSON |
| followup_reschedule | Update follow-up dates |
| knowledge_capture | Capture + distill from inbox |
| knowledge_cleanup | Delete cards/threads |
| knowledge_lookup | Find articles by date |
| unsupported_capability | Calendar, Salesforce, upload |
| purchase_ops | Fix purchase ID prefix |
| clarification | Ambiguous/truncated requests |

## GPT-OSS-120B Notes

- **temp=1.0 ONLY** — lower temps cause empty outputs (Harmony format issue)
- `Reasoning: high` removed — may conflict with vLLM
- Model uses Harmony response format — reasoning in separate channel
- `OpenAIChatCompletionsModel` required (not Responses API)
- Fallback parser handles cases where model produces text instead of tool calls
- search limit increased to 2000 for counting (files with 1000+ lines)

## Environment Variables

| Var | Default | Notes |
|---|---|---|
| `OPENAI_API_KEY` | — | Model API key |
| `OPENAI_BASE_URL` | — | vLLM endpoint URL |
| `MODEL_ID` | gpt-4.1-2025-04-14 | Model name |
| `BITGN_API_KEY` | — | Leaderboard key |
| `BITGN_RUN_NAME` | agent-v2-run | Run name on leaderboard |
| `AGENT_CONCURRENCY` | 10 | Parallel agents (slider up to 30) |
| `AGENT_MAX_TURNS` | 50 | Max ReAct steps per task |
| `AGENT_REQUEST_TIMEOUT` | 120 | LLM timeout (seconds) |

## Documentation

- [Benchmark Overview](docs/benchmark-overview.md) — Protocol, runtime, workspaces
- [Tasks Catalog](docs/tasks-catalog.md) — All 43 tasks with expected outcomes
- [Scoring Rules](docs/scoring-rules.md) — grounding_refs, common failures
- [Architecture](docs/architecture.md) — v1 legacy pipeline
- [Configuration](docs/configuration.md) — Env vars, commands
- [**Optimization Guide**](docs/optimization-guide.md) — All learnings, error patterns, fixes

## Current Score: ~81% (35/43)

Best run: 79.1% stable, 83% peak with lucky variance.

### Solved Patterns
- Inbox security (obvious + subtle injection + OTP mismatch)
- Cross-account verification (sender vs account ownership)
- Trap workspace detection (non-standard workspace with docs chain)
- Outbox seq.json workflow (read README → read seq → write → bump)
- Counting with search limit=2000
- Grounding refs for manager contacts

### Remaining: t23 (multiple contacts disambiguation)
Agent finds 2 contacts with same name, follows docs guardrail "clarify if multiple match".
Scorer expects OK — agent should resolve by context (account attributes, compliance_flags).
**Fix needed**: override guardrail when inbox message context provides clear disambiguation.

## Dashboard Features

- **Run tab**: live SSE logs per task, score, tool calls, timing
- **Compare tab**: heatmap across runs, stability analysis
- **Skills tab**: view/test all prompts, system prompt viewer
- **Sidebar**: run history, delete, compare checkboxes
- **Per-task**: Copy log button, Platform log link (harness_url)
- **SQLite**: all events persisted in benchmark-runs/pac1.db
