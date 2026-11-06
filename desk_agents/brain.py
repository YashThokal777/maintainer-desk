"""Claude Code in headless mode (`claude -p`) as a teammate's brain.

One Claude session per chat thread, resumed on every new message in that
thread, so "yes" means yes to what the agent proposed a minute ago.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("desk_agents.brain")


@dataclass
class Answer:
    text: str
    session_id: str | None
    is_error: bool = False


def claude_argv(
    *, system: str, tools: tuple[str, ...], session_id: str | None, max_turns: int = 40,
    executable: str | None = None,
) -> list[str]:
    argv = [
        executable or shutil.which("claude") or "claude",
        "-p",
        "--output-format", "json",
        "--append-system-prompt", system,
        "--allowedTools", ",".join(tools),
        "--max-turns", str(max_turns),
    ]
    if session_id:
        argv += ["--resume", session_id]
    return argv


def parse_output(stdout: str) -> Answer:
    """Read `claude -p --output-format json`: one JSON object, or JSON lines."""
    text = stdout.strip()
    candidates = [text] + [ln for ln in reversed(text.splitlines()) if ln.startswith("{")]
    for raw in candidates:
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        if isinstance(data, list):  # some versions print the whole event list
            data = next((d for d in reversed(data) if d.get("type") == "result"), {})
        if isinstance(data, dict) and ("result" in data or "session_id" in data):
            return Answer(
                text=str(data.get("result") or "").strip(),
                session_id=data.get("session_id"),
                is_error=bool(data.get("is_error")) or data.get("subtype") not in (None, "success"),
            )
    return Answer(text=text[-2000:], session_id=None, is_error=True)


async def think(
    prompt: str, *, system: str, tools: tuple[str, ...], cwd: Path, env: dict[str, str],
    session_id: str | None, timeout: float = 1200,
) -> Answer:
    argv = claude_argv(system=system, tools=tools, session_id=session_id)
    log.debug("Running %s in %s", argv[0], cwd)
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(cwd),
        env={**os.environ, **env},
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(prompt.encode("utf-8")), timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return Answer(f"I ran out of time ({int(timeout // 60)} min) on this one.", session_id, True)
    answer = parse_output(out.decode("utf-8", errors="replace"))
    if proc.returncode != 0 and not answer.text:
        answer = Answer(err.decode("utf-8", errors="replace")[-1500:], session_id, True)
    if answer.session_id is None:
        answer.session_id = session_id
    return answer
