from __future__ import annotations

import asyncio
import json
import shlex
import time
from typing import Any

from connectrpc.code import Code
from connectrpc.errors import ConnectError
from bitgn.vm.pcm_connect import PcmRuntimeClientSync
from bitgn.vm.pcm_pb2 import (
    AnswerRequest,
    ContextRequest,
    DeleteRequest,
    FindRequest,
    ListRequest,
    MkDirRequest,
    MoveRequest,
    Outcome,
    ReadRequest,
    SearchRequest,
    TreeRequest,
    WriteRequest,
)
from google.protobuf.json_format import MessageToDict


OUTCOME_MAP = {
    "OUTCOME_OK": Outcome.OUTCOME_OK,
    "OUTCOME_DENIED_SECURITY": Outcome.OUTCOME_DENIED_SECURITY,
    "OUTCOME_NONE_CLARIFICATION": Outcome.OUTCOME_NONE_CLARIFICATION,
    "OUTCOME_NONE_UNSUPPORTED": Outcome.OUTCOME_NONE_UNSUPPORTED,
    "OUTCOME_ERR_INTERNAL": Outcome.OUTCOME_ERR_INTERNAL,
}

TRANSIENT_CODES = {Code.UNAVAILABLE, Code.INTERNAL, Code.UNKNOWN, Code.DEADLINE_EXCEEDED}


def _fmt_tree(entry: Any, prefix: str = "", is_last: bool = True) -> list[str]:
    branch = "\u2514\u2500\u2500 " if is_last else "\u251c\u2500\u2500 "
    lines = [f"{prefix}{branch}{entry.name}"]
    child_prefix = f"{prefix}{'    ' if is_last else '\u2502   '}"
    children = list(entry.children)
    for i, child in enumerate(children):
        lines.extend(_fmt_tree(child, child_prefix, i == len(children) - 1))
    return lines


class AsyncPcmRuntime:
    """Async wrapper around the synchronous PCM gRPC client."""

    def __init__(self, harness_url: str, retries: int = 4) -> None:
        self._client = PcmRuntimeClientSync(harness_url)
        self._retries = retries

    def _sync_dispatch(self, method: str, request: Any) -> Any:
        last_exc: Exception | None = None
        for attempt in range(self._retries + 1):
            try:
                return getattr(self._client, method)(request)
            except ConnectError as exc:
                last_exc = exc
                if exc.code not in TRANSIENT_CODES or attempt >= self._retries:
                    raise
                time.sleep(0.25 * (attempt + 1))
        raise last_exc  # type: ignore[misc]

    async def _call(self, method: str, request: Any) -> Any:
        return await asyncio.to_thread(self._sync_dispatch, method, request)

    # ── Tool implementations ───────────────────────────────────────────

    async def get_context(self) -> str:
        result = await self._call("context", ContextRequest())
        return json.dumps(MessageToDict(result), indent=2)

    async def tree(self, root: str = "/", level: int = 2) -> str:
        req = TreeRequest(root=root, level=level)
        result = await self._call("tree", req)
        rt = result.root
        if not rt.name:
            return "."
        lines = [rt.name]
        children = list(rt.children)
        for i, child in enumerate(children):
            lines.extend(_fmt_tree(child, is_last=i == len(children) - 1))
        level_arg = f" -L {level}" if level > 0 else ""
        return f"tree{level_arg} {root}\n" + "\n".join(lines)

    async def list_dir(self, path: str = "/") -> str:
        result = await self._call("list", ListRequest(name=path))
        entries = [
            f"{e.name}/" if e.is_dir else e.name for e in result.entries
        ]
        return f"ls {path}\n" + "\n".join(entries) if entries else f"ls {path}\n."

    async def read_file(
        self, path: str, start_line: int = 0, end_line: int = 0, number: bool = False,
    ) -> str:
        req = ReadRequest(path=path, number=number, start_line=start_line, end_line=end_line)
        result = await self._call("read", req)
        if start_line > 0 or end_line > 0:
            s = start_line if start_line > 0 else 1
            e = end_line if end_line > 0 else "$"
            cmd = f"sed -n '{s},{e}p' {path}"
        elif number:
            cmd = f"cat -n {path}"
        else:
            cmd = f"cat {path}"
        return f"{cmd}\n{result.content}"

    async def find_files(
        self, name: str, root: str = "/", kind: str = "all", limit: int = 10,
    ) -> str:
        kind_map = {"all": 0, "files": 1, "dirs": 2}
        req = FindRequest(root=root, name=name, type=kind_map.get(kind, 0), limit=limit)
        result = await self._call("find", req)
        return json.dumps(MessageToDict(result), indent=2)

    async def search(self, pattern: str, root: str = "/", limit: int = 10) -> str:
        req = SearchRequest(root=root, pattern=pattern, limit=limit)
        result = await self._call("search", req)
        lines = [f"{m.path}:{m.line}:{m.line_text}" for m in result.matches]
        safe_pattern = shlex.quote(pattern)
        safe_root = shlex.quote(root)
        count = len(lines)
        header = f"rg -n --no-heading -e {safe_pattern} {safe_root}\n"
        footer = f"\n\n[{count} matches found]"
        return header + "\n".join(lines) + footer

    async def write_file(
        self, path: str, content: str, start_line: int = 0, end_line: int = 0,
    ) -> str:
        req = WriteRequest(path=path, content=content, start_line=start_line, end_line=end_line)
        result = await self._call("write", req)
        return json.dumps(MessageToDict(result), indent=2)

    async def delete(self, path: str) -> str:
        result = await self._call("delete", DeleteRequest(path=path))
        return json.dumps(MessageToDict(result), indent=2)

    async def mkdir(self, path: str) -> str:
        result = await self._call("mk_dir", MkDirRequest(path=path))
        return json.dumps(MessageToDict(result), indent=2)

    async def move(self, from_path: str, to_path: str) -> str:
        result = await self._call("move", MoveRequest(from_name=from_path, to_name=to_path))
        return json.dumps(MessageToDict(result), indent=2)

    async def answer(
        self, message: str, outcome: str, refs: list[str],
    ) -> str:
        req = AnswerRequest(
            message=message,
            outcome=OUTCOME_MAP.get(outcome, Outcome.OUTCOME_OK),
            refs=refs,
        )
        result = await self._call("answer", req)
        return json.dumps(MessageToDict(result), indent=2) if result else "{}"
