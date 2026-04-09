# Phantom — Autonomous Agent for BitGN PAC1 Challenge

[Русский](docs/README_RU.md) | [中文](docs/README_ZH.md)

An autonomous file-system agent built with [OpenAI Agents SDK](https://github.com/openai/openai-agents-python) that solves the [BitGN PAC1 Challenge](https://bitgn.com/challenge/PAC) — a benchmark for AI agents operating in sandboxed virtual environments.

**Current score: ~86% (37/43 tasks)**

![Dashboard — Task Results](assets/dashboard-tasks.jpg)

![Dashboard — Heatmap Compare](assets/dashboard-heatmap.jpg)

## What is PAC1?

[BitGN](https://bitgn.com) runs agent benchmarks where autonomous agents solve real-world tasks inside isolated sandbox VMs. Each task gives the agent a file-system workspace and a natural language instruction. The agent must explore, reason, and execute — no human in the loop.

![BitGN Platform](assets/bitgn-platform.png)

PAC1 covers 43 tasks across:
- **CRM operations** — lookups, email sending, invoice handling
- **Knowledge management** — capture, distill, cleanup
- **Inbox processing** — with prompt injection traps and OTP verification
- **Security** — detecting and denying hostile payloads

Learn more: [bitgn.com/challenge/PAC](https://bitgn.com/challenge/PAC)

## Architecture

```
User task → LLM Classifier (picks skill) → Agent(system_prompt + skill_prompt + task)
  → ReAct loop: LLM → tool call → result → LLM → ... → report_completion
```

- **12 specialized skills** with hot-reloadable prompts (edit `.md` files, no restart needed)
- **Dual classifier** — LLM-first with regex fallback and override logic
- **Self-correcting agent** — can call `list_skills` / `get_skill_instructions` to switch workflows mid-task
- **Auto grounding refs** — tracks read/written files, injects references if model forgets
- **Retry on empty** — retries up to 3x if model returns text without tool calls
- **Live dashboard** — React + Vite with SSE streaming, heatmap compare, token tracking

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- Node.js 18+ (for dashboard)
- An OpenAI-compatible LLM endpoint
- [BitGN API key](https://bitgn.com) for benchmark access

### 1. Install dependencies

```bash
cd pac1-py
uv sync
cd dashboard && npm install && cd ..
```

### 2. Set environment variables

```bash
export OPENAI_API_KEY=<your-llm-api-key>
export OPENAI_BASE_URL=<your-llm-endpoint>   # e.g. https://api.openai.com/v1
export MODEL_ID=<model-name>                  # e.g. gpt-4.1-2025-04-14
export BITGN_API_KEY=<your-bitgn-key>         # get one at bitgn.com
```

Optional:

| Variable | Default | Description |
|---|---|---|
| `AGENT_CONCURRENCY` | `10` | Parallel agents (max 30) |
| `AGENT_MAX_TURNS` | `50` | Max ReAct steps per task |
| `AGENT_REQUEST_TIMEOUT` | `120` | LLM timeout (seconds) |
| `BITGN_RUN_NAME` | `agent-v2-run` | Run name on leaderboard |

### 3. Run with dashboard

```bash
# Terminal 1 — Backend API
cd pac1-py
uv run python server.py
# → http://localhost:8000

# Terminal 2 — Frontend
cd pac1-py/dashboard
npm run dev
# → http://localhost:5173
```

Open the dashboard, click **Run**, watch your agent solve tasks in real-time.

### 4. Run headless (CLI only)

```bash
cd pac1-py
uv run python main_v2.py
```

## Project Structure

```
pac1-py/
├── server.py                 # FastAPI + SSE backend for dashboard
├── main_v2.py                # CLI benchmark runner
├── agent_v2/
│   ├── agent.py              # Agent creation, run loop with retry logic
│   ├── system_prompt.md      # System prompt (hot-reloadable)
│   ├── prompts.py            # Prompt loader + task prompt builder
│   ├── tools.py              # 13 tools (file ops, search, skills, completion)
│   ├── hooks.py              # Live logging hooks + token tracking
│   ├── context.py            # Task context, telemetry, file tracking
│   ├── config.py             # Environment config
│   ├── runtime.py            # Async PCM gRPC wrapper
│   ├── db.py                 # SQLite persistence (runs, tasks, events)
│   └── skills/
│       ├── registry.py       # Skill registry (hot-reload from .md files)
│       ├── classifier.py     # Regex-based task classifier
│       ├── llm_classifier.py # LLM-based task classifier
│       └── *.md              # 12 skill prompts
├── dashboard/                # React + Vite + Tailwind CSS
│   └── src/App.jsx           # Single-file dashboard app
└── pyproject.toml
```

## Dashboard

The dashboard provides real-time visibility into agent runs:

- **Run tab** — live SSE event stream per task with score, tool calls, timing, and token usage
- **Compare tab** — heatmap view across multiple runs with stability analysis
- **Skills tab** — browse and test all skill prompts, view system prompt
- **Sidebar** — run history sorted by date, showing temperature and model per run
- **Controls** — adjustable temperature (slider + input) and concurrency

## How It Works

### Skills System

Each task is classified into one of 12 skills, each with a specialized prompt:

| Skill | Description |
|---|---|
| `security_denial` | Detect and deny prompt injection, hostile payloads |
| `inbox_processing` | Process CRM inbox messages with security checks |
| `email_outbound` | Send emails via outbox with contact resolution |
| `crm_lookup` | Find accounts, contacts, emails, managers |
| `invoice_creation` | Create typed invoice JSON records |
| `followup_reschedule` | Update follow-up dates in accounts and reminders |
| `knowledge_capture` | Capture and distill from inbox into cards/threads |
| `knowledge_cleanup` | Delete cards, threads, distill artifacts |
| `knowledge_lookup` | Find articles by date in captured content |
| `unsupported_capability` | Calendar, Salesforce sync — not available |
| `purchase_ops` | Fix purchase ID prefix issues |
| `clarification` | Request too short or ambiguous |

### Hot-Reload

All prompts are read from disk at runtime:
- **Skill prompts**: `pac1-py/agent_v2/skills/*.md`
- **System prompt**: `pac1-py/agent_v2/system_prompt.md`

Edit any `.md` file → next run picks it up automatically. No server restart needed.

### Self-Correcting Classification

If the pre-classifier picks the wrong skill, the agent can fix it mid-task:

1. Agent notices the skill instructions don't match the task
2. Calls `list_skills` to see all available skills
3. Calls `get_skill_instructions("correct_skill")` to load the right workflow
4. Continues with correct instructions

## Based On

Started from the [BitGN sample-agent](https://github.com/bitgn/sample-agent) and extended with the skills system, dashboard, and optimizations.

## License

MIT
