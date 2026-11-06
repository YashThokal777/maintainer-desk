"""The watcher itself: poll GitHub, post new items, answer the people in the room."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from . import cards, commands
from .config import Settings
from .github import GitHub, Item, new_items, untriaged
from .state import State
from .switch import Agent, Message, SwitchError

log = logging.getLogger("desk_watcher")


@dataclass
class Desk:
    settings: Settings
    state: State
    agent: Agent
    github: GitHub
    paused: bool = False
    intake_room_id: str | None = None
    _check_now: asyncio.Event = field(default_factory=asyncio.Event)

    async def find_intake_room(self) -> str | None:
        """The intake room's id, by name; the only room when there is just one."""
        rooms = await self.agent.rooms()
        want = self.settings.intake_room.lower()
        for room in rooms:
            if (room.get("name") or "").lower() == want:
                return room["room_id"]
        if len(rooms) == 1:
            return rooms[0]["room_id"]
        return None

    async def poll_once(self) -> list[Item]:
        """Post every open item not posted before. Returns what was posted."""
        repo = self.settings.repo
        items = await self.github.open_items()
        if self.state.is_first_run(repo) and not self.settings.announce_existing:
            # The triager reads the existing backlog itself at kickoff; only
            # what arrives from now on is posted one by one.
            self.state.mark_seen(repo, {i.number for i in items})
            self.state.save(self.settings.state_file)
            log.info("First run: %d existing items marked as seen", len(items))
            return []
        if self.paused:
            return []
        if self.intake_room_id is None:
            self.intake_room_id = await self.find_intake_room()
            if self.intake_room_id is None:
                log.warning(
                    "No room named %r yet. Run the template, or set DESK_INTAKE_ROOM.",
                    self.settings.intake_room,
                )
                return []
        posted: list[Item] = []
        for item in new_items(items, self.state.seen_for(repo)):
            item = await self.github.with_pr_details(item)
            await self.agent.post(self.intake_room_id, cards.item_card(item, self.settings.triager))
            self.state.mark_seen(repo, {item.number})
            self.state.posted += 1
            self.state.save(self.settings.state_file)
            posted.append(item)
            log.info("Posted %s #%d", item.kind, item.number)
        return posted

    async def poll_forever(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            try:
                await self.poll_once()
            except SwitchError as exc:
                log.error("%s", exc)
            except Exception as exc:  # noqa: BLE001 - one bad poll must not stop the desk
                log.exception("Poll failed: %s", exc)
            self._check_now.clear()
            waiters = [asyncio.create_task(stop.wait()), asyncio.create_task(self._check_now.wait())]
            await asyncio.wait(waiters, timeout=self.settings.poll_seconds, return_when=asyncio.FIRST_COMPLETED)
            for w in waiters:
                w.cancel()

    async def reply(self, msg: Message, text: str) -> None:
        await self.agent.post(msg.room_id, text)

    async def on_message(self, msg: Message) -> None:
        command = commands.parse(msg.body)
        log.info("%s asked: %s -> %s", msg.sender_name or msg.sender, msg.body, command)
        try:
            if command == "help":
                await self.reply(msg, cards.HELP.format(repo=self.settings.repo, triager=self.settings.triager))
            elif command == "status":
                items = await self.github.open_items(limit=100)
                await self.reply(
                    msg,
                    cards.status_card(self.settings.repo, items, untriaged(items), self.state.posted, self.paused),
                )
            elif command == "check":
                await self.reply(msg, f"Checking {self.settings.repo} now.")
                self._check_now.set()
            elif command == "pause":
                self.paused = True
                await self.reply(msg, "Paused. New items wait until someone says `resume`.")
            elif command == "resume":
                self.paused = False
                self._check_now.set()
                await self.reply(msg, "Resumed. Posting anything new now.")
        except Exception as exc:  # noqa: BLE001 - answer, rather than go quiet
            log.exception("Command %s failed", command)
            await self.reply(msg, f"That failed: {exc}")

    async def run(self, stop: asyncio.Event) -> None:
        listener = asyncio.create_task(self.agent.listen(self.on_message, stop))
        poller = asyncio.create_task(self.poll_forever(stop))
        await asyncio.wait({listener, poller}, return_when=asyncio.FIRST_COMPLETED)
        stop.set()
        await asyncio.gather(listener, poller, return_exceptions=True)
