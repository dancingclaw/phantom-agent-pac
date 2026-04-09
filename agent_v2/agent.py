from __future__ import annotations

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
_client_key: tuple[str, str] | None = None


def _get_client(cfg: Config) -> AsyncOpenAI:
    global _client, _client_key
    key = (cfg.openai_api_key, cfg.openai_base_url)
    if _client is None or _client_key != key:
        set_tracing_disabled(True)
        _client = AsyncOpenAI(
            api_key=cfg.openai_api_key,
            base_url=cfg.openai_base_url or None,
            timeout=cfg.request_timeout,
        )
        _client_key = key
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


FORCE_TOOL_PROMPT = """You already solved the task and produced this answer:

<YOUR_ANSWER>
{output}
</YOUR_ANSWER>

Now call submit_answer with this answer. Extract message, outcome, and grounding_refs from your answer above."""


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

    try:
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

        print(f"  {task_id} output: {output[:200]}")
        if on_event:
            on_event("agent_output", {
                "task_id": task_id,
                "output": output[:1000],
                "completion_submitted": context.completion_submitted,
            })

        # If agent finished without calling submit_answer, re-run with ONLY submit_answer tool
        if not context.completion_submitted:
            print(f"  {task_id} [FORCE_TOOL] re-running with only submit_answer")
            if on_event:
                on_event("fallback_submit", {
                    "task_id": task_id,
                    "message": "Re-running agent to force tool call",
                    "outcome": "FORCE_TOOL",
                })
            from .tools import submit_answer
            force_agent = Agent[TaskContext](
                name="ForceSubmit",
                instructions="You must call submit_answer with the provided answer. Nothing else.",
                model=agent.model,
                tools=[submit_answer],
                model_settings=ModelSettings(temperature=0.0, max_tokens=4096, tool_choice="required"),
            )
            await Runner.run(
                force_agent,
                input=FORCE_TOOL_PROMPT.format(output=output[:2000]),
                context=context,
                max_turns=1,
                hooks=hooks,
            )
            if not context.completion_submitted:
                print(f"  {task_id} [FORCE_TOOL] still no tool call, giving up")

    except Exception as exc:
        print(f"  Agent error: {exc}")
    finally:
        telemetry.finish()

    return telemetry
