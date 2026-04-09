# BitGN PAC1 Benchmark Overview

## What It Is

PAC1 is a competitive benchmark from the BitGN platform. It evaluates the ability of an LLM agent to perform tasks in isolated virtual runtimes (sandbox file systems).

The agent connects to the BitGN harness, receives 43 tasks, solves each one in its own sandbox, and the harness evaluates the result.

## Interaction Protocol

```
BitGN Harness                         Agent
     │                                  │
     │  ── get_benchmark ──────────►    │   (task list + eval policy)
     │  ◄── benchmark metadata ─────    │
     │                                  │
     │  ── start_run ──────────────►    │   (create run for leaderboard)
     │  ◄── run_id + trial_ids ─────    │
     │                                  │
     │  ── start_trial(trial_id) ──►    │   (start task)
     │  ◄── instruction + runtime_url   │   (task text + sandbox URL)
     │                                  │
     │      Agent works with runtime    │
     │      (tree, list, read, write,   │
     │       search, find, delete,      │
     │       move, mkdir, context,      │
     │       report_completion)         │
     │                                  │
     │  ── end_trial ──────────────►    │   (finish + get score)
     │  ◄── score + score_detail ───    │
     │                                  │
     │  ── submit_run ─────────────►    │   (submit to leaderboard)
     │  ◄── RUN_STATE_EVALUATED ────    │
```

## Runtime (PCM)

Each task is executed in an isolated file sandbox (`bitgn.vm.pcm`). Available operations:

| Command | Description |
|---|---|
| `context` | Current sandbox time (unixTime + ISO) |
| `tree` | Directory tree (root, level) |
| `list` | Directory contents |
| `read` | Read file (entire file or line range) |
| `find` | Search files by name |
| `search` | Full-text search (regex) |
| `write` | Create/overwrite file (entire file or line range) |
| `delete` | Delete file or directory |
| `mkdir` | Create directory |
| `move` | Move/rename |
| `report_completion` | Complete task with result |

## Workspace Types

Tasks are executed in three workspace types:

### knowledge_repo (t01-t09, t33, t42-t43)
```
/00_inbox/          — incoming unprocessed files
/01_capture/        — canonical captured sources
/02_distill/        — synthesis: cards/ + threads/
/90_memory/         — agent configuration (Soul.md)
/99_process/        — process documents
/AGENTS.md          — workspace rules
```

### typed_crm_fs (t10-t30, t34-t40)
```
/accounts/          — JSON account records
/contacts/          — JSON contact records
/my-invoices/       — JSON invoices
/inbox/             — incoming messages
/outbox/            — outgoing email (seq.json for numbering)
/docs/              — documentation on channels, workflow
/opportunities/     — deals
/reminders/         — follow-up reminders
```

### purchase_ops (t31)
```
/docs/              — workflow documentation
/processing/        — processing lanes
/purchases/         — purchase records
```

## Scoring

- Each task: 0.00 or 1.00 (binary scoring)
- Final score: average * 100%
- The scorer checks specific artifacts in the sandbox after completion
- `grounding_refs` in report_completion must contain exact file paths
- `message` must contain a specific answer with paths (for lookup tasks)

## Outcomes

| Outcome | When to use |
|---|---|
| `OUTCOME_OK` | Task completed, evidence exists in sandbox |
| `OUTCOME_DENIED_SECURITY` | Prompt injection, exfiltration, hostile content |
| `OUTCOME_NONE_CLARIFICATION` | Request is ambiguous, clarification needed |
| `OUTCOME_NONE_UNSUPPORTED` | Feature not supported by runtime |
| `OUTCOME_ERR_INTERNAL` | Internal agent error |
