# Обзор бенчмарка BitGN PAC1

## Что это

PAC1 — соревновательный бенчмарк от платформы BitGN. Оценивает способность LLM-агента выполнять задачи в изолированных виртуальных рантаймах (sandbox файловые системы).

Агент подключается к BitGN harness, получает 43 задачи, решает каждую в своём sandbox, harness оценивает результат.

## Протокол взаимодействия

```
BitGN Harness                         Agent
     │                                  │
     │  ── get_benchmark ──────────►    │   (список задач + eval policy)
     │  ◄── benchmark metadata ─────    │
     │                                  │
     │  ── start_run ──────────────►    │   (создание прогона на лидерборд)
     │  ◄── run_id + trial_ids ─────    │
     │                                  │
     │  ── start_trial(trial_id) ──►    │   (запуск задачи)
     │  ◄── instruction + runtime_url   │   (текст задачи + URL sandbox)
     │                                  │
     │      Agent работает с runtime    │
     │      (tree, list, read, write,   │
     │       search, find, delete,      │
     │       move, mkdir, context,      │
     │       report_completion)         │
     │                                  │
     │  ── end_trial ──────────────►    │   (завершить + получить оценку)
     │  ◄── score + score_detail ───    │
     │                                  │
     │  ── submit_run ─────────────►    │   (отправить на лидерборд)
     │  ◄── RUN_STATE_EVALUATED ────    │
```

## Runtime (PCM)

Каждая задача выполняется в изолированном файловом sandbox (`bitgn.vm.pcm`). Доступные операции:

| Команда | Описание |
|---|---|
| `context` | Текущее время sandbox (unixTime + ISO) |
| `tree` | Дерево каталогов (root, level) |
| `list` | Содержимое каталога |
| `read` | Чтение файла (целиком или диапазон строк) |
| `find` | Поиск файлов по имени |
| `search` | Full-text поиск (regex) |
| `write` | Создание/перезапись файла (целиком или диапазон строк) |
| `delete` | Удаление файла или каталога |
| `mkdir` | Создание каталога |
| `move` | Перемещение/переименование |
| `report_completion` | Завершение задачи с результатом |

## Типы workspace

Задачи выполняются в трёх типах workspace:

### knowledge_repo (t01-t09, t33, t42-t43)
```
/00_inbox/          — входящие необработанные файлы
/01_capture/        — каноничные захваченные источники
/02_distill/        — синтез: cards/ + threads/
/90_memory/         — конфигурация агента (Soul.md)
/99_process/        — процессные документы
/AGENTS.md          — правила workspace
```

### typed_crm_fs (t10-t30, t34-t40)
```
/accounts/          — JSON-записи аккаунтов
/contacts/          — JSON-записи контактов
/my-invoices/       — JSON-инвойсы
/inbox/             — входящие сообщения
/outbox/            — исходящие email (seq.json для нумерации)
/docs/              — документация по каналам, workflow
/opportunities/     — сделки
/reminders/         — напоминания о follow-up
```

### purchase_ops (t31)
```
/docs/              — документация workflow
/processing/        — lanes обработки
/purchases/         — записи покупок
```

## Оценка

- Каждая задача: 0.00 или 1.00 (бинарная оценка)
- Итоговый скор: среднее * 100%
- Скорер проверяет конкретные артефакты в sandbox после завершения
- `grounding_refs` в report_completion должны содержать точные пути к файлам
- `message` должно содержать конкретный ответ с путями (для lookup-задач)

## Outcomes (исходы)

| Outcome | Когда использовать |
|---|---|
| `OUTCOME_OK` | Задача выполнена, есть доказательства в sandbox |
| `OUTCOME_DENIED_SECURITY` | Prompt injection, exfiltration, враждебный контент |
| `OUTCOME_NONE_CLARIFICATION` | Запрос неоднозначен, нужно уточнение |
| `OUTCOME_NONE_UNSUPPORTED` | Функция не поддерживается runtime |
| `OUTCOME_ERR_INTERNAL` | Внутренняя ошибка агента |
