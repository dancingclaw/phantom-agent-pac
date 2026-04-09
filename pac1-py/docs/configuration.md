# Конфигурация и запуск

## Переменные окружения

### Обязательные

| Переменная | Описание |
|---|---|
| `OPENAI_API_KEY` | API-ключ провайдера |
| `OPENAI_BASE_URL` | URL OpenAI-совместимого API (если не OpenAI) |
| `MODEL_ID` | Имя модели (default: `gpt-4.1-2025-04-14`) |

### Для лидерборда

| Переменная | Описание |
|---|---|
| `BITGN_API_KEY` | Ключ для лидерборда BitGN |
| `BITGN_RUN_NAME` | Имя прогона на лидерборде |

### Настройки агента

| Переменная | Default | Описание |
|---|---|---|
| `AGENT_MAX_STEPS` | 30 | Макс. шагов ReAct loop на задачу |
| `AGENT_MAX_TOKENS` | 4096 | Макс. токенов на ответ LLM |
| `AGENT_REQUEST_TIMEOUT_SECONDS` | 60 | Таймаут запроса к LLM |
| `AGENT_JSON_REPAIR_RETRIES` | 2 | Попытки починить невалидный JSON |
| `AGENT_FASTPATH_MODE` | framed | `off` / `framed` / `all` |
| `AGENT_USE_GBNF` | auto | GBNF grammar (для локальных моделей) |
| `BENCHMARK_HOST` | https://api.bitgn.com | URL BitGN harness |
| `BENCHMARK_ID` | bitgn/pac1-dev | ID бенчмарка |
| `PCM_RETRY_ATTEMPTS` | 4 | Retries при transient ошибках runtime |

## Команды запуска

```bash
cd pac1-py

# Установка зависимостей
make sync

# Полный прогон на лидерборд
OPENAI_API_KEY=... OPENAI_BASE_URL=... MODEL_ID=... BITGN_API_KEY=... make run

# Тестовый прогон (playground, без лидерборда)
uv run python main.py t01 t03 t42

# Прогон с максимальным использованием LLM
AGENT_FASTPATH_MODE=off uv run python main.py

# Прогон конкретной задачи для отладки
AGENT_FASTPATH_MODE=off uv run python main.py t42
```

## Артефакты

После прогона сохраняются в `benchmark-runs/`:
- `latest_metrics.json` — полные метрики (totals + per-task)
- `latest_metrics.csv` — CSV-выгрузка
- `latest_full_run.txt` — полный лог (только для полных прогонов)
