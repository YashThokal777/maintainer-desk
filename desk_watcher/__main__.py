"""desk-watcher: `register` once, then `run`.

    python -m desk_watcher register   # needs SWITCH_REGISTRATION_KEY
    python -m desk_watcher run        # posts new issues/PRs and answers the room
    python -m desk_watcher check      # one GitHub read, prints what would be posted
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys

import httpx

from . import cards
from .config import Settings
from .desk import Desk
from .github import GitHub, new_items
from .state import State
from .switch import Agent, SwitchError, register

DESCRIPTION = "Posts every new issue and pull request into the maintainer desk"


async def cmd_register(s: Settings, state: State) -> int:
    if state.api_key:
        print(f"Already registered as {s.agent_name} ({state.agent_id}). Delete {s.state_file} to start over.")
        return 0
    if not s.registration_key:
        print("Set SWITCH_REGISTRATION_KEY: Gateway (http://localhost:3000) > API Keys > Create.")
        return 2
    async with httpx.AsyncClient(base_url=s.api_url, timeout=30) as http:
        health = await http.get("/health")
        if health.status_code != 200:
            print(f"{s.api_url}/health answered {health.status_code}. Is SWITCH_API_URL the API, not the Gateway?")
            return 2
        state.agent_id, state.api_key = await register(http, s.registration_key, s.agent_name, DESCRIPTION)
        state.save(s.state_file)
    print(f"Registered {s.agent_name} ({state.agent_id}). Its key is saved in {s.state_file}.")
    print("Next:")
    print(f"  1. If you own it, open Switch Console > Your Agents > {s.agent_name} and set who can")
    print("     address it to Anyone, so every maintainer can ask it for status.")
    print("  2. Run the Maintainer Desk template, then `python -m desk_watcher run`.")
    return 0


async def cmd_run(s: Settings, state: State) -> int:
    if not (state.agent_id and state.api_key):
        print("Not registered yet. Run `python -m desk_watcher register` first.")
        return 2
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except (NotImplementedError, RuntimeError):
            pass  # Windows: Ctrl+C raises KeyboardInterrupt instead
    async with httpx.AsyncClient(base_url=s.api_url, timeout=30) as http, GitHub(s.repo, s.github_token) as gh:
        agent = Agent(http, s.ws_url, state.agent_id, state.api_key, state.connection_id)
        desk = Desk(s, state, agent, gh)
        logging.getLogger("desk_watcher").info(
            "Watching %s every %ds; posting to %s for @%s", s.repo, s.poll_seconds, s.intake_room, s.triager
        )
        await desk.run(stop)
    return 0


async def cmd_check(s: Settings, state: State) -> int:
    async with GitHub(s.repo, s.github_token) as gh:
        items = await gh.open_items()
        fresh = new_items(items, state.seen_for(s.repo))
        print(f"{len(items)} open items in {s.repo}; {len(fresh)} not posted yet.\n")
        for item in fresh[:5]:
            print(cards.item_card(await gh.with_pr_details(item), s.triager))
            print("---")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="desk-watcher", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["register", "run", "check"])
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)
    # Windows consoles default to a code page that can't print the cards.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if not args.verbose:
        logging.getLogger("httpx").setLevel(logging.WARNING)
    s = Settings.from_env()
    state = State.load(s.state_file)
    handler = {"register": cmd_register, "run": cmd_run, "check": cmd_check}[args.command]
    try:
        return asyncio.run(handler(s, state))
    except KeyboardInterrupt:
        return 0
    except SwitchError as exc:
        print(exc, file=sys.stderr)
        return 1
    except httpx.ConnectError as exc:
        print(f"Could not reach {exc.request.url.host if exc.request else s.api_url}: {exc}. "
              "Is Switch running (Switch Console open, Docker started)?", file=sys.stderr)
        return 1
    except httpx.HTTPStatusError as exc:
        print(f"{exc.request.url} answered {exc.response.status_code}: {exc.response.text[:200]}",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
