# Architecture

## C4 — System Context

```
┌─────────────┐         ┌──────────────────┐         ┌──────────────┐
│  Developer   │────────▶│  Phantom Agent   │────────▶│  BitGN       │
│  (Browser)   │◀────────│  System          │◀────────│  Platform    │
└─────────────┘  HTTP    └──────────────────┘  gRPC   └──────────────┘
                 SSE      │                            │
                          │  Runs tasks in             │  Provides sandboxed
                          │  isolated VMs              │  file-system VMs
                          │                            │  Scores results
                          ▼                            │
                 ┌──────────────────┐                  │
                 │  LLM Provider    │                  │
                 │  (OpenAI-compat) │◀─────────────────┘
                 └──────────────────┘
                   Chat Completions API
```

**Phantom Agent** is an autonomous system that:
1. Receives 43 tasks from the BitGN benchmark platform
2. Runs each task inside an isolated sandbox VM via gRPC
3. Uses an LLM (via OpenAI-compatible API) to reason and execute
4. Reports results back to the platform for scoring

## C4 — Container Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│  Phantom Agent System                                           │
│                                                                 │
│  ┌──────────────┐    SSE     ┌──────────────────────────────┐  │
│  │  Dashboard    │◀─────────▶│  FastAPI Server               │  │
│  │  (React/Vite) │           │  server.py                    │  │
│  │              │    HTTP    │                                │  │
│  │  - Run tab    │──────────▶│  - /api/runs (CRUD)           │  │
│  │  - Compare    │           │  - /api/runs/:id/stream (SSE) │  │
│  │  - Skills     │           │  - /api/config (temperature)  │  │
│  │  - Heatmap    │           │  - /api/skills, /api/prompt   │  │
│  └──────────────┘           └──────────┬───────────────────┘  │
│                                         │                       │
│                              ┌──────────▼───────────────────┐  │
│                              │  Agent Runner                 │  │
│                              │  agent_v2/agent.py            │  │
│                              │                               │  │
│                              │  ┌─────────┐  ┌───────────┐  │  │
│                              │  │Classifier│  │ Skills    │  │  │
│                              │  │LLM+Regex │  │ 12x .md  │  │  │
│                              │  └─────────┘  └───────────┘  │  │
│                              │  ┌─────────┐  ┌───────────┐  │  │
│                              │  │Tools 13x│  │ Hooks     │  │  │
│                              │  │file,srch │  │ SSE+logs  │  │  │
│                              │  └─────────┘  └───────────┘  │  │
│                              └──────────┬───────────────────┘  │
│                                         │                       │
│                              ┌──────────▼───────────────────┐  │
│                              │  SQLite (db.py)               │  │
│                              │  runs, tasks, events          │  │
│                              └──────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
         │                              │
         │ gRPC (protobuf)              │ OpenAI Chat Completions
         ▼                              ▼
┌──────────────────┐          ┌──────────────────┐
│  BitGN Harness   │          │  LLM Provider    │
│  - Sandbox VMs   │          │  (vLLM / OpenAI) │
│  - Scoring       │          │                  │
│  - Leaderboard   │          │                  │
└──────────────────┘          └──────────────────┘
```

## C4 — Component Diagram (Agent Runner)

```
┌──────────────────────────────────────────────────────────────┐
│  Agent Runner (agent_v2/)                                     │
│                                                               │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Task Classification                                    │  │
│  │                                                         │  │
│  │  1. LLM Classifier (llm_classifier.py)                  │  │
│  │     └─ Sends task text to LLM, gets skill_id + conf     │  │
│  │  2. Regex Classifier (classifier.py)                    │  │
│  │     └─ Pattern matching fallback, overrides LLM          │  │
│  │        "clarification" if regex finds a real match       │  │
│  └────────────────────────┬───────────────────────────────┘  │
│                            │ skill_id                         │
│                            ▼                                  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Skill Prompt Loader (registry.py)                      │  │
│  │                                                         │  │
│  │  Hot-reload: reads .md from disk on every call          │  │
│  │  12 skills: inbox_processing, email_outbound,           │  │
│  │  crm_lookup, security_denial, knowledge_capture, ...    │  │
│  └────────────────────────┬───────────────────────────────┘  │
│                            │ system_prompt + skill_prompt      │
│                            ▼                                  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  OpenAI Agents SDK Runner                               │  │
│  │                                                         │  │
│  │  Agent(instructions, model, tools, model_settings)      │  │
│  │  └─ Runner.run(agent, input, context, hooks, max_turns) │  │
│  │                                                         │  │
│  │  ReAct Loop:                                            │  │
│  │    LLM call ──▶ tool call ──▶ result ──▶ LLM call ─▶…  │  │
│  │                                                         │  │
│  │  Resilience:                                            │  │
│  │  - Retry up to 3x if 0 tool calls                      │  │
│  │  - Auto grounding_refs from tracked files               │  │
│  │  - Fallback text parser if report_completion not called  │  │
│  └────────────────────────┬───────────────────────────────┘  │
│                            │                                  │
│  ┌─────────────┐ ┌────────▼────────┐ ┌────────────────────┐ │
│  │ Hooks        │ │ Tools (13)      │ │ Context            │ │
│  │ hooks.py     │ │ tools.py        │ │ context.py         │ │
│  │              │ │                 │ │                    │ │
│  │ - on_llm_*   │ │ - get_context   │ │ - runtime_url     │ │
│  │ - on_tool_*  │ │ - tree          │ │ - task_text       │ │
│  │ - SSE emit   │ │ - list_directory│ │ - telemetry       │ │
│  │ - token track│ │ - read_file     │ │   (tool_calls,    │ │
│  │              │ │ - find_files    │ │    tokens, time)  │ │
│  │              │ │ - search        │ │ - files_read[]    │ │
│  │              │ │ - write_file    │ │ - files_written[] │ │
│  │              │ │ - delete_file   │ │ - completion_flag │ │
│  │              │ │ - make_directory│ │                    │ │
│  │              │ │ - move_file     │ └────────────────────┘ │
│  │              │ │ - list_skills   │                        │
│  │              │ │ - get_skill_*   │                        │
│  │              │ │ - report_compl. │                        │
│  └─────────────┘ └─────────────────┘                        │
└──────────────────────────────────────────────────────────────┘
```

## Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| **LLM** | OpenAI Agents SDK (`openai-agents>=0.0.7`) | ReAct agent loop, tool execution, model management |
| **LLM Client** | OpenAI Python SDK (`openai>=2.26.0`) | Chat completions via `OpenAIChatCompletionsModel` |
| **Backend** | FastAPI (`fastapi>=0.115.0`) + Uvicorn | REST API, SSE streaming |
| **Frontend** | React 19 + Vite 8 + Tailwind CSS 4 | Live dashboard, heatmap, controls |
| **Persistence** | SQLite (stdlib `sqlite3`) | Runs, tasks, events — WAL mode |
| **Platform SDK** | `bitgn-local-sdk` + `connectrpc` | gRPC client for BitGN sandbox VMs |
| **Serialization** | Protobuf (`protobuf>=6.33.0`) | BitGN harness protocol |
| **Validation** | Pydantic (`pydantic>=2.12.5`) | Request/response models |

## Data Flow — Single Task Execution

```
1. Server receives POST /api/runs
   └─ Creates BenchmarkRun, starts async _run_benchmark_async()

2. Harness connection
   └─ start_run() → get trial_ids
   └─ For each task: start_trial() → get instruction + runtime_url

3. Classification (agent.py:97-118)
   ├─ LLM classifier: sends task text → gets skill_id
   ├─ If "clarification" → regex classifier overrides
   └─ Loads skill prompt from .md file (hot-reload)

4. Agent execution (agent.py:126-160)
   ├─ Runner.run(agent, task_prompt, context, hooks, max_turns=50)
   ├─ ReAct loop: LLM → tool call → runtime gRPC → result → LLM
   ├─ Hooks emit SSE events in real-time
   ├─ If 0 tool calls → retry up to 3x
   └─ If no report_completion → fallback parser extracts answer

5. Completion
   ├─ report_completion(message, outcome, grounding_refs)
   ├─ Auto-ref injection if refs empty
   ├─ end_trial() → score from harness
   └─ SSE: task_done event with score, tokens, timing

6. Run finish
   ├─ submit_run() → leaderboard
   └─ SQLite: persist final scores
```

## Key Design Decisions

| Decision | Rationale |
|---|---|
| **OpenAI Agents SDK** over raw chat completions | Built-in ReAct loop, tool management, hooks system |
| **Dual classifier** (LLM + regex) | LLM handles nuance, regex catches patterns LLM misclassifies (e.g. ALL CAPS) |
| **Hot-reload prompts** from `.md` files | Iterate on prompts without restarting — edit file, next run picks it up |
| **Agent self-selects skills** via tools | Recovers from classifier mistakes mid-task |
| **SQLite WAL mode** | Concurrent reads during benchmark runs without locking |
| **SSE streaming** (not WebSocket) | Simpler, works with EventSource API, auto-reconnect |
| **Single-file dashboard** (`App.jsx`) | All UI in one place — fast iteration, no component hunting |
| **Temperature=1.0 default** | Required for gpt-oss-120b (Harmony format — lower temps cause empty outputs) |
