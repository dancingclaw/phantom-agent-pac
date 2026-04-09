# Agent Architecture

## Type: Hybrid (Deterministic Workflow + LLM ReAct)

The agent is NOT a pure ReAct and NOT a pure workflow. It is a three-level hybrid where 93% of tasks are solved deterministically.

## Task Processing Pipeline

```
Task arrives
        │
        ▼
┌──────────────────────┐
│ 1. Pre-bootstrap     │ safety.py: regex for injection, deictic, truncated
│    preflight         │ If triggered → instant response without LLM
└──────┬───────────────┘
       │ not triggered
       ▼
┌──────────────────────┐
│ 2. Bootstrap         │ grounding.py: ls /, tree -L 2 /, read AGENTS.md, context
│                      │ Determines repository_profile and capabilities
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│ 3. Post-bootstrap    │ policy.py: workspace capabilities check
│    preflight         │ If unsupported → OUTCOME_NONE_UNSUPPORTED
└──────┬───────────────┘
       │ not triggered
       ▼
┌──────────────────────┐
│ 4. Knowledge inbox   │ knowledge_repo.py: check for suspicious inbox items
│    security          │ If injection in inbox → OUTCOME_DENIED_SECURITY
└──────┬───────────────┘
       │ not triggered
       ▼
┌──────────────────────┐
│ 5. Frame shortcut    │ framing.py: regex patterns → TaskFrame without LLM
│    OR LLM frame      │ If pattern not recognized → LLM creates frame
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│ 6. Ground frame      │ grounding.py: reads files from frame.relevant_roots
│                      │ Loads AGENTS.md from nested folders
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│ 7. Fastpath          │ fastpath.py: 10 specialized handlers
│    handlers          │ If any triggered → task solved without LLM
└──────┬───────────────┘
       │ none triggered
       ▼
┌──────────────────────┐
│ 8. LLM ReAct Loop    │ loop.py:710-772
│    (up to 30 steps)  │ LLM → NextStep → execute tool → result → LLM → ...
│                      │ Exit: report_completion or max_steps
└──────────────────────┘
```

## Key Files

| File | Purpose |
|---|---|
| `main.py` | Benchmark orchestration: connecting to harness, running tasks, collecting metrics |
| `loop.py` | Main function `run_agent()`: the entire pipeline from bootstrap to completion |
| `config.py` | Configuration from env (model, base_url, max_steps, fastpath_mode) |
| `models.py` | Pydantic schemas: TaskFrame, NextStep, ReportTaskCompletion, all Req_* |
| `llm.py` | OpenAI client: JSON parsing, retry, GBNF grammar support |
| `runtime.py` | PCM runtime adapter: command dispatch, response formatting |
| `policy.py` | Prompts for LLM (system, frame, execution, tool_result) |
| `safety.py` | Regex detection of injection, truncated requests |
| `framing.py` | Shortcut frames (high confidence) and fallback frames |
| `grounding.py` | Bootstrap, workspace reading, ground frame |
| `capabilities.py` | Workspace profile and task intent determination |
| `fastpath.py` | Dispatcher for 10 handlers (tries each in order) |
| `verifier.py` | Verification: generic completion guard, mutation verification |
| `workflows.py` | Regex parsers for task type recognition |

## Specialized Handlers (fastpath)

| Handler | File | What it solves |
|---|---|---|
| `handle_direct_capture_snippet` | knowledge_repo.py | Capture snippet from website |
| `handle_knowledge_repo_capture` | knowledge_repo.py | Take from inbox, capture, distill |
| `handle_knowledge_repo_cleanup` | knowledge_repo.py | Remove cards and threads |
| `handle_invoice_creation` | typed_mutations.py | Create invoice |
| `handle_followup_reschedule` | typed_mutations.py | Reschedule follow-up |
| `handle_contact_email_lookup` | crm_handlers.py | Email lookup by name/account |
| `handle_direct_outbound_email` | crm_handlers.py | Send email to contact/account |
| `handle_channel_status_lookup` | crm_handlers.py | Count blacklisted channels |
| `handle_typed_crm_inbox` | crm_inbox.py | Process CRM inbox messages |
| `handle_purchase_prefix_regression` | typed_mutations.py | Fix purchase ID prefix |

## ReAct Loop (when it reaches the LLM)

```
messages = [system_prompt, workspace_context, frame, execution_prompt]

for step in range(max_steps):
    NextStep = LLM(messages)        # LLM generates plan + tool call
    
    if NextStep.function == report_completion:
        if verifier.ok(NextStep):
            runtime.execute(NextStep)   # send the response
            break
        else:
            messages += verifier_feedback  # "need specific refs"
            continue
    
    result = runtime.execute(NextStep.function)  # execute tool
    messages += tool_result_prompt(result)        # add to context
```

## fastpath_mode Setting

| Value | Behavior |
|---|---|
| `"framed"` (default) | Fastpath after framing. Most tasks are solved without the ReAct loop |
| `"all"` | Fastpath also BEFORE framing |
| `"off"` | Fastpath disabled. All tasks go through the LLM ReAct loop |

For model testing, `AGENT_FASTPATH_MODE=off` is recommended.
