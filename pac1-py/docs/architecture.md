# Архитектура агента

## Тип: Гибрид (Deterministic Workflow + LLM ReAct)

Агент — это НЕ чистый ReAct и НЕ чистый workflow. Это трёхуровневый гибрид, где 93% задач решаются детерминистически.

## Pipeline обработки задачи

```
Задача поступает
        │
        ▼
┌──────────────────────┐
│ 1. Pre-bootstrap     │ safety.py: regex на injection, deictic, truncated
│    preflight         │ Если сработало → мгновенный ответ без LLM
└──────┬───────────────┘
       │ не сработало
       ▼
┌──────────────────────┐
│ 2. Bootstrap         │ grounding.py: ls /, tree -L 2 /, read AGENTS.md, context
│                      │ Определяет repository_profile и capabilities
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│ 3. Post-bootstrap    │ policy.py: проверка capabilities workspace
│    preflight         │ Если unsupported → OUTCOME_NONE_UNSUPPORTED
└──────┬───────────────┘
       │ не сработало
       ▼
┌──────────────────────┐
│ 4. Knowledge inbox   │ knowledge_repo.py: проверка suspicious inbox items
│    security          │ Если injection в inbox → OUTCOME_DENIED_SECURITY
└──────┬───────────────┘
       │ не сработало
       ▼
┌──────────────────────┐
│ 5. Frame shortcut    │ framing.py: regex-паттерны → TaskFrame без LLM
│    ИЛИ LLM frame     │ Если паттерн не распознан → LLM создаёт frame
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│ 6. Ground frame      │ grounding.py: читает файлы из frame.relevant_roots
│                      │ Загружает AGENTS.md вложенных папок
└──────┬───────────────┘
       │
       ▼
┌──────────────────────┐
│ 7. Fastpath          │ fastpath.py: 10 специализированных хендлеров
│    handlers          │ Если какой-то сработал → задача решена без LLM
└──────┬───────────────┘
       │ ни один не сработал
       ▼
┌──────────────────────┐
│ 8. LLM ReAct Loop    │ loop.py:710-772
│    (до 30 шагов)     │ LLM → NextStep → execute tool → result → LLM → ...
│                      │ Выход: report_completion или max_steps
└──────────────────────┘
```

## Ключевые файлы

| Файл | Назначение |
|---|---|
| `main.py` | Оркестрация бенчмарка: подключение к harness, запуск задач, сбор метрик |
| `loop.py` | Главная функция `run_agent()`: весь pipeline от bootstrap до completion |
| `config.py` | Конфигурация из env (модель, base_url, max_steps, fastpath_mode) |
| `models.py` | Pydantic-схемы: TaskFrame, NextStep, ReportTaskCompletion, все Req_* |
| `llm.py` | OpenAI-клиент: JSON parsing, retry, GBNF grammar support |
| `runtime.py` | Адаптер PCM runtime: dispatch команд, форматирование ответов |
| `policy.py` | Промпты для LLM (system, frame, execution, tool_result) |
| `safety.py` | Regex-детекция injection, truncated requests |
| `framing.py` | Shortcut-фреймы (высокая уверенность) и fallback-фреймы |
| `grounding.py` | Bootstrap, чтение workspace, ground frame |
| `capabilities.py` | Определение профиля workspace и intent задачи |
| `fastpath.py` | Диспетчер 10 хендлеров (пробует каждый по очереди) |
| `verifier.py` | Проверка: generic completion guard, mutation verification |
| `workflows.py` | Regex-парсеры для распознавания типов задач |

## Специализированные хендлеры (fastpath)

| Хендлер | Файл | Что решает |
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

## ReAct Loop (когда доходит до LLM)

```
messages = [system_prompt, workspace_context, frame, execution_prompt]

for step in range(max_steps):
    NextStep = LLM(messages)        # LLM генерирует план + tool call
    
    if NextStep.function == report_completion:
        if verifier.ok(NextStep):
            runtime.execute(NextStep)   # отправляем ответ
            break
        else:
            messages += verifier_feedback  # "нужны конкретные refs"
            continue
    
    result = runtime.execute(NextStep.function)  # выполняем tool
    messages += tool_result_prompt(result)        # добавляем в контекст
```

## Режим fastpath_mode

| Значение | Поведение |
|---|---|
| `"framed"` (default) | Fastpath после фрейминга. Большинство задач решаются без ReAct loop |
| `"all"` | Fastpath ещё и ДО фрейминга |
| `"off"` | Fastpath отключен. Все задачи идут через LLM ReAct loop |

Для тестирования модели рекомендуется `AGENT_FASTPATH_MODE=off`.
