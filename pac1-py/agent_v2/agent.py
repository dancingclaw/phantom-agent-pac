from __future__ import annotations

import json
import re

from openai import AsyncOpenAI
from agents import (
    Agent,
    ModelSettings,
    RunConfig,
    Runner,
    set_tracing_disabled,
)
from agents.models.openai_chatcompletions import OpenAIChatCompletionsModel

from .config import Config
from .context import TaskContext, Telemetry
from .prompts import get_system_prompt, build_task_prompt
from .tools import ALL_TOOLS


_client: AsyncOpenAI | None = None


def _get_client(cfg: Config) -> AsyncOpenAI:
    global _client
    if _client is None:
        set_tracing_disabled(True)
        _client = AsyncOpenAI(
            api_key=cfg.openai_api_key,
            base_url=cfg.openai_base_url or None,
            timeout=cfg.request_timeout,
        )
    return _client


def create_agent(cfg: Config, temperature: float = 1.0) -> Agent[TaskContext]:
    client = _get_client(cfg)
    model = OpenAIChatCompletionsModel(
        model=cfg.model,
        openai_client=client,
    )
    return Agent[TaskContext](
        name="PAC1-Agent",
        instructions=get_system_prompt(),
        model=model,
        tools=ALL_TOOLS,
        model_settings=ModelSettings(
            temperature=temperature,
            max_tokens=4096,
        ),
    )


def _extract_fallback_answer(text: str) -> tuple[str, str, list[str]]:
    """Try to parse agent's text output into (message, outcome, refs)."""
    # Try JSON parse
    try:
        for match in re.finditer(r"\{[^{}]*\}", text, re.DOTALL):
            obj = json.loads(match.group())
            if "message" in obj and "outcome" in obj:
                return (
                    str(obj["message"]),
                    str(obj["outcome"]),
                    list(obj.get("grounding_refs", [])),
                )
    except (json.JSONDecodeError, KeyError):
        pass
    # Extract file paths from text as refs
    refs = re.findall(r"/[\w._-]+(?:/[\w._-]+)+", text)
    return text[:500], "OUTCOME_OK", refs[:5]


async def run_task(
    cfg: Config,
    agent: Agent[TaskContext],
    runtime_url: str,
    task_text: str,
    task_id: str = "",
    on_event=None,
) -> Telemetry:
    """Run a single benchmark task. Returns telemetry.

    Args:
        on_event: Optional callback (event_type, data_dict) for SSE streaming.
    """
    from .hooks import LiveHooks

    telemetry = Telemetry()
    context = TaskContext(
        runtime_url=runtime_url,
        task_text=task_text,
        telemetry=telemetry,
    )
    hooks = LiveHooks(task_id=task_id, on_event=on_event)

    # Classify task — LLM first, regex fallback
    from .skills import classify_task, get_skill_prompt
    from .skills.llm_classifier import classify_with_llm

    # Try LLM classification
    client = _get_client(cfg)
    try:
        match = await classify_with_llm(client, cfg.model, task_text)
        classifier_type = "llm"
    except Exception:
        match = classify_task(task_text)
        classifier_type = "regex"

    # Fallback to regex if LLM returned nothing or low-value "clarification"
    # LLM often misclassifies terse/ALL-CAPS requests as clarification
    if not match.skill_id or match.skill_id == "clarification":
        regex_match = classify_task(task_text)
        if regex_match.skill_id and regex_match.skill_id != "clarification":
            match = regex_match
            classifier_type = "regex"
        elif not match.skill_id:
            match = regex_match
            classifier_type = "regex"

    skill_prompt = get_skill_prompt(match.skill_id) if match.skill_id else None
    if match.skill_id:
        print(f"  {task_id} skill: {match.skill_id} ({match.confidence:.0%}) [{classifier_type}]")
    if on_event:
        on_event("task_classified", {
            "task_id": task_id,
            "skill_id": match.skill_id,
            "skill_confidence": match.confidence,
            "classifier": classifier_type,
        })

    max_retries = 3
    try:
        for attempt in range(1, max_retries + 1):
            result = await Runner.run(
                agent,
                input=build_task_prompt(task_text, skill_prompt),
                context=context,
                max_turns=cfg.max_turns,
                hooks=hooks,
                run_config=RunConfig(
                    model_settings=ModelSettings(
                        temperature=agent.model_settings.temperature if agent.model_settings else 1.0,
                        max_tokens=4096,
                    ),
                ),
            )
            output = str(result.final_output)

            # If model made zero tool calls and didn't submit, retry
            if not context.completion_submitted and telemetry.tool_calls == 0 and attempt < max_retries:
                print(f"  {task_id} [RETRY {attempt}/{max_retries}] 0 tool calls, retrying...")
                if on_event:
                    on_event("fallback_submit", {
                        "task_id": task_id,
                        "message": f"Retry {attempt}/{max_retries}: model returned text without tool calls",
                        "outcome": "RETRY",
                    })
                hooks.step = 0
                continue
            break

        print(f"  {task_id} output: {output[:200]}")
        if on_event:
            on_event("agent_output", {
                "task_id": task_id,
                "output": output[:1000],
                "completion_submitted": context.completion_submitted,
            })

        # Fallback: if agent never called report_completion, submit now
        if not context.completion_submitted:
            print("  [FALLBACK] report_completion not called, submitting from text output")
            message, outcome, refs = _extract_fallback_answer(output)
            await context.runtime.answer(message, outcome, refs)
            if on_event:
                on_event("fallback_submit", {"task_id": task_id, "message": message, "outcome": outcome})

    except Exception as exc:
        print(f"  Agent error: {exc}")
        if not context.completion_submitted:
            try:
                await context.runtime.answer(
                    message=f"Agent internal error: {exc}",
                    outcome="OUTCOME_ERR_INTERNAL",
                    refs=["/AGENTS.md"],
                )
            except Exception:
                pass
    finally:
        telemetry.finish()

    return telemetry
