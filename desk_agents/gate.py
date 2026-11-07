"""The human gate, enforced in code.

The agents' Claude sessions may only run read-only `gh` commands (see
`roles.GH_READ`). A change to GitHub happens in one place: here. The agent
ends its reply with a **Proposed action:**; the desk process stores that
command for the thread, and runs it itself only when a person answers in the
same thread, after the proposal, with a clear yes. Anything else ("ok sure",
an edit, a question) goes back to the agent, which can only propose again.
"""

from __future__ import annotations

import asyncio
import os
import re
import shlex
import shutil
from dataclasses import dataclass
from pathlib import Path

# The only GitHub writes the desk will run, even on a yes. No merge, no
# close, no delete, no `gh api`.
WRITES = {
    ("issue", "edit"), ("issue", "comment"),
    ("pr", "edit"), ("pr", "comment"), ("pr", "review"),
}

YES = {"yes", "y", "yep", "yes please", "approve", "approved", "go", "go ahead", "apply", "lgtm"}
NO = {"no", "nope", "hold", "stop", "cancel", "wait", "don't", "dont", "do not", "not yet"}

PROPOSAL = re.compile(r"proposed action:?\**\s*(.*)", re.IGNORECASE | re.DOTALL)
FENCE = re.compile(r"```[\w-]*\n(.*?)```", re.DOTALL)
INLINE = re.compile(r"`([^`\n]+)`")


class GateError(ValueError):
    """A proposed command the desk will not run."""


@dataclass
class Ran:
    command: str
    returncode: int
    output: str


def proposed_command(reply: str) -> str | None:
    """The command after **Proposed action:**, from a ```sh block or `inline code`."""
    m = PROPOSAL.search(reply)
    if not m:
        return None
    rest = m.group(1)
    fence, inline = FENCE.search(rest), INLINE.search(rest)
    # Whichever code comes first after the label is the proposal.
    found = min((x for x in (fence, inline) if x), key=lambda x: x.start(), default=None)
    if not found:
        return None
    return found.group(1).strip() or None


def check(command: str, repo: str) -> list[str]:
    """Split a proposed command and make sure it is one allowed GitHub write."""
    if command.count("\n") and sum(ln.lstrip().startswith("gh ") for ln in command.splitlines()) > 1:
        raise GateError("one command per proposal")
    try:
        argv = shlex.split(command.replace("\\\n", " "))
    except ValueError as exc:
        raise GateError(f"can't parse the command: {exc}") from exc
    if len(argv) < 3 or argv[0] != "gh":
        raise GateError("not a gh command")
    if (argv[1], argv[2]) not in WRITES:
        raise GateError(f"`gh {argv[1]} {argv[2]}` is not a write the desk runs")
    for i, arg in enumerate(argv):
        target = None
        if arg in ("-R", "--repo") and i + 1 < len(argv):
            target = argv[i + 1]
        elif arg.startswith("--repo="):
            target = arg.partition("=")[2]
        if target is not None and target.lower() != repo.lower():
            raise GateError(f"the desk only writes to {repo}")
    return argv


def verdict(body: str, own_name: str) -> str | None:
    """"yes", "no", or None when the message isn't a plain answer."""
    text = re.sub(rf"@{re.escape(own_name)}\b", " ", body, flags=re.IGNORECASE).lower()
    text = re.sub(r"[^\w\s']", " ", text)
    text = " ".join(text.split())
    if text in YES:
        return "yes"
    if text in NO:
        return "no"
    return None


async def run(argv: list[str], *, cwd: Path, env: dict[str, str], timeout: float = 120) -> Ran:
    """Run one checked `gh` write, without a shell."""
    command = shlex.join(argv)
    exe = shutil.which("gh") or "gh"
    proc = await asyncio.create_subprocess_exec(
        exe, *argv[1:], cwd=str(cwd), env={**os.environ, **env},
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return Ran(command, -1, f"timed out after {int(timeout)} s")
    return Ran(command, proc.returncode or 0, out.decode("utf-8", errors="replace").strip())
