"""The desk's Claude-backed teammates.

    python -m desk_agents register triager   # once per role
    python -m desk_agents run triager         # keep running; answers in Switch
    desk-post --room desk-review "text"       # used by the agents themselves
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path

import httpx

from desk_watcher.config import load_dotenv
from desk_watcher.switch import Agent, SwitchError, register

from .roles import ROLES
from .teammate import Teammate, TeammateState

PROJECT = Path(__file__).resolve().parent.parent


def registration_key() -> str | None:
    """SWITCH_REGISTRATION_KEY, or the seeded token of Console's local server."""
    key = os.environ.get("SWITCH_REGISTRATION_KEY")
    if key:
        return key
    appdata = os.environ.get("APPDATA")
    if appdata:
        env = Path(appdata) / "switchdash/local-switch-server/native/run/switch-core.env"
        if env.is_file():
            for line in env.read_text(encoding="utf-8").splitlines():
                if line.startswith("AGENT_REGISTRATION_TOKEN="):
                    return line.partition("=")[2].strip() or None
    return None


class Config:
    def __init__(self, role_key: str) -> None:
        load_dotenv(PROJECT / ".env")
        self.role = ROLES[role_key]
        self.api_url = os.environ.get("SWITCH_API_URL", "http://localhost:8000").rstrip("/")
        self.ws_url = self.api_url.replace("https://", "wss://", 1).replace("http://", "ws://", 1)
        self.repo = os.environ.get("DESK_REPO", "").strip()
        if "/" not in self.repo:
            raise SystemExit("Set DESK_REPO to the GitHub repository, as owner/name.")
        self.team = os.environ.get("DESK_TEAM", "desk").strip()
        self.name = self.role.name(self.team)
        self.state_file = PROJECT / f".desk-state.{role_key}.json"
        # Each agent works in its own clone. Kept short: Windows git refuses
        # paths over 260 characters.
        agents_dir = Path(os.environ.get("DESK_AGENTS_DIR") or Path.home() / ".maintainer-desk")
        self.workdir = agents_dir / self.name / self.repo.split("/")[1]
        self.peers = tuple(r.name(self.team) for r in ROLES.values() if r.key != role_key) + (
            os.environ.get("DESK_AGENT_NAME", "desk-watcher"),
        )


def ensure_clone(cfg: Config) -> None:
    if (cfg.workdir / ".git").is_dir():
        subprocess.run(["git", "-C", str(cfg.workdir), "fetch", "--quiet", "--all"], check=False)
        return
    cfg.workdir.parent.mkdir(parents=True, exist_ok=True)
    # HTTPS, so no SSH host-key prompt; `gh` uses the API for everything else.
    url = f"https://github.com/{cfg.repo}.git"
    subprocess.run(["git", "clone", "--quiet", url, str(cfg.workdir)], check=True)


async def cmd_register(cfg: Config) -> int:
    state = TeammateState.load(cfg.state_file)
    if state.api_key:
        print(f"Already registered as {cfg.name} ({state.agent_id}).")
        return 0
    key = registration_key()
    if not key:
        print("Set SWITCH_REGISTRATION_KEY (or run Switch Console's local server).")
        return 2
    async with httpx.AsyncClient(base_url=cfg.api_url, timeout=30) as http:
        description = cfg.role.description.format(repo=cfg.repo)
        state.agent_id, state.api_key = await register(http, key, cfg.name, description)
    state.save(cfg.state_file)
    print(f"Registered {cfg.name} ({state.agent_id}). Its key is in {cfg.state_file.name}.")
    return 0


def agent_env(cfg: Config) -> dict[str, str]:
    scripts = str(Path(sys.executable).parent)
    return {
        "PATH": scripts + os.pathsep + os.environ.get("PATH", ""),
        "DESK_AGENT_ROLE": cfg.role.key,
        "SWITCH_API_URL": cfg.api_url,
        "PYTHONIOENCODING": "utf-8",
        # A headless turn must never sit at a git or ssh prompt.
        "GIT_TERMINAL_PROMPT": "0",
        "GH_PROMPT_DISABLED": "1",
    }


async def cmd_run(cfg: Config) -> int:
    state = TeammateState.load(cfg.state_file)
    if not state.api_key:
        print(f"Not registered yet. Run `python -m desk_agents register {cfg.role.key}` first.")
        return 2
    ensure_clone(cfg)
    async with httpx.AsyncClient(base_url=cfg.api_url, timeout=60) as http:
        agent = Agent(http, cfg.ws_url, state.agent_id, state.api_key, state.connection_id,
                      client_name=f"maintainer-desk-{cfg.role.key}", delivery_filter="all")
        mate = Teammate(role=cfg.role, name=cfg.name, team=cfg.team, repo=cfg.repo, agent=agent,
                        state=state, state_file=cfg.state_file, workdir=cfg.workdir,
                        env=agent_env(cfg), peers=cfg.peers)
        logging.getLogger("desk_agents").info("%s is listening; working in %s", cfg.name, cfg.workdir)
        await mate.run(asyncio.Event())
    return 0


async def cmd_post(cfg: Config, room: str | None, here: bool, text: str) -> int:
    """Post as this agent. Used by the agent's own Claude session."""
    state = TeammateState.load(cfg.state_file)
    async with httpx.AsyncClient(base_url=cfg.api_url, timeout=30) as http:
        agent = Agent(http, cfg.ws_url, state.agent_id, state.api_key, state.connection_id)
        # The teammate process holds this connection's socket open.
        agent.connected.set()
        if here:
            room_id, thread = os.environ.get("DESK_ROOM_ID"), os.environ.get("DESK_THREAD_ID")
            if not room_id:
                print("--here only works inside a desk turn (DESK_ROOM_ID is unset).")
                return 2
            await agent.reply(room_id, text, thread)
            print("Posted in this thread.")
            return 0
        rooms = await agent.rooms()
        wanted = (room or "").lstrip("#").lower()
        match = [r for r in rooms if wanted in ((r.get("name") or "").lower(), r["room_id"].lower())]
        if not match:
            names = ", ".join(sorted(r.get("name") or r["room_id"] for r in rooms))
            print(f"No room {room!r}. Rooms I'm in: {names}")
            return 2
        await agent.post(match[0]["room_id"], text)
        print(f"Posted in #{match[0].get('name')}.")
    return 0


async def cmd_open(cfg: Config) -> int:
    """Let every maintainer address the desk agents.

    Switch only lets an agent's owner change who may address it, and never
    the agent itself. The desk agents share an owner, so each one opens up
    the others with `update_agent_detail`.
    """
    from desk_watcher.state import State

    keys: dict[str, tuple[str, str]] = {}
    for role in ROLES:
        s = TeammateState.load(PROJECT / f".desk-state.{role}.json")
        if s.api_key:
            keys[ROLES[role].name(cfg.team)] = (s.agent_id, s.api_key)
    watcher = State.load(PROJECT / ".desk-state.json")
    if watcher.api_key:
        keys[os.environ.get("DESK_AGENT_NAME", "desk-watcher")] = (watcher.agent_id, watcher.api_key)
    if len(keys) < 2:
        print("Register at least two desk agents first.")
        return 2
    names = list(keys)
    async with httpx.AsyncClient(base_url=cfg.api_url, timeout=30) as http:
        for i, target in enumerate(names):
            caller = names[(i + 1) % len(names)]
            cid, ckey = keys[caller]
            agent = Agent(http, cfg.ws_url, cid, ckey, "unused")
            await agent.op("update_agent_detail", agent_id=keys[target][0], addressing="anyone")
            print(f"{target}: anyone may address it (set by {caller})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="desk_agents", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["register", "run", "open-addressing"])
    parser.add_argument("role", nargs="?", choices=sorted(ROLES), default="triager")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    setup_logging(args.verbose)
    cfg = Config(args.role)
    commands = {"register": cmd_register, "run": cmd_run, "open-addressing": cmd_open}
    return guarded(commands[args.command](cfg), cfg)


def post_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="desk-post", description="Post into Switch as this desk agent.")
    where = parser.add_mutually_exclusive_group(required=True)
    where.add_argument("--room", help="room name, e.g. desk-review (starts a new message there)")
    where.add_argument("--here", action="store_true", help="reply in the current thread")
    parser.add_argument("--as", dest="role", default=os.environ.get("DESK_AGENT_ROLE"), choices=sorted(ROLES))
    parser.add_argument("text", nargs="+")
    args = parser.parse_args(argv)
    if not args.role:
        parser.error("--as is required outside a desk turn")
    setup_logging(False)
    cfg = Config(args.role)
    return guarded(cmd_post(cfg, args.room, args.here, " ".join(args.text)), cfg)


def setup_logging(verbose: bool) -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not verbose:
        logging.getLogger("httpx").setLevel(logging.WARNING)


def guarded(coro, cfg: Config) -> int:
    try:
        return asyncio.run(coro)
    except KeyboardInterrupt:
        return 0
    except SwitchError as exc:
        print(exc, file=sys.stderr)
        return 1
    except httpx.ConnectError as exc:
        print(f"Could not reach {cfg.api_url}: {exc}. Is Switch running?", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
