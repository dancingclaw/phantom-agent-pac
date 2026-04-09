from __future__ import annotations

from pathlib import Path

_PROMPT_FILE = Path(__file__).parent / "system_prompt.md"


def get_system_prompt() -> str:
    """Read system prompt from file — hot-reloadable."""
    return _PROMPT_FILE.read_text(encoding="utf-8").strip()


# Keep SYSTEM_PROMPT as a property-like for backwards compat
# But anyone importing it gets the current value at import time
# Use get_system_prompt() for dynamic reads
SYSTEM_PROMPT = get_system_prompt()


def build_task_prompt(task_text: str, skill_prompt: str | None = None) -> str:
    skill_block = ""
    if skill_prompt:
        skill_block = f"\n{skill_prompt}\n"

    return f"""<TASK>
{task_text}
</TASK>
{skill_block}
<GOAL>
Solve this task. Orient first, reason about the approach, execute, verify, complete.
</GOAL>"""
