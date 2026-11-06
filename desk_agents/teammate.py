"""A Claude-backed desk teammate on the Switch agent protocol.

It reads every message in its rooms (`filter=all`) and answers when it is
@mentioned, or when a person writes in a thread it is already working in
(that is how a bare "yes" reaches it). Each thread gets its own resumed
Claude session.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from desk_watcher.switch import Agent, Message, SwitchError

from . import brain
from .roles import Role

log = logging.getLogger("desk_agents")

NO_REPLY = "NO_REPLY"
NOTICES = ("isn't in this room", "not permitted to direct messages", "joined the room")
MAX_POST = 15000


@dataclass
class TeammateState:
    agent_id: str | None = None
    api_key: str | None = None
    connection_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    # "<room_id>:<thread_root>" -> Claude session id
    sessions: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "TeammateState":
        if not path.is_file():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def save(self, path: Path) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        tmp.replace(path)


def mentions(body: str, name: str) -> bool:
    return re.search(rf"(?<![\w-])@{re.escape(name)}(?![\w-])", body, re.IGNORECASE) is not None


def thread_key(msg: Message) -> str:
    return f"{msg.room_id}:{msg.thread_root}"


@dataclass
class Teammate:
    role: Role
    name: str
    team: str
    repo: str
    agent: Agent
    state: TeammateState
    state_file: Path
    workdir: Path
    env: dict[str, str] = field(default_factory=dict)
    # Other desk agents' names: a message @mentioning only them isn't for us.
    peers: tuple[str, ...] = ()
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    room_names: dict[str, str] = field(default_factory=dict)

    def should_answer(self, msg: Message) -> bool:
        if msg.sender in (self.name, self.agent.agent_id) or msg.sender_name == self.name:
            return False
        # Switch's own delivery notices ("X isn't in this room…") are about a
        # message, not a request; answering them only adds noise.
        if msg.sender_kind == "platform" and any(n in msg.body for n in NOTICES):
            return False
        if mentions(msg.body, self.name) or msg.addressed:
            return True
        if any(mentions(msg.body, p) for p in self.peers):
            return False
        # A person following up in a thread this agent is working in.
        return msg.sender_kind == "user" and thread_key(msg) in self.state.sessions

    async def on_message(self, msg: Message) -> None:
        if self.should_answer(msg):
            log.info("Queued: %s in %s: %s", msg.sender_name or msg.sender,
                     self.room_name(msg.room_id), msg.body[:80].replace("\n", " "))
            await self.queue.put(msg)

    def room_name(self, room_id: str) -> str:
        return self.room_names.get(room_id, room_id)

    async def refresh_rooms(self) -> None:
        try:
            for room in await self.agent.rooms():
                self.room_names[room["room_id"]] = room.get("name") or room["room_id"]
        except SwitchError as exc:
            log.warning("list_rooms failed: %s", exc)

    def system_prompt(self) -> str:
        return self.role.instructions.format(name=self.name, team=self.team, repo=self.repo)

    def prompt(self, msg: Message) -> str:
        who = msg.sender_name or msg.sender
        kind = msg.sender_kind or "unknown"
        return (
            f"New message in Switch room #{self.room_name(msg.room_id)}"
            f" (thread {msg.thread_root}).\n"
            f"From: {who} ({kind})\n\n{msg.body}\n\n"
            "Answer as the reply to post in this thread, or NO_REPLY."
        )

    async def handle(self, msg: Message) -> None:
        if msg.room_id not in self.room_names:
            await self.refresh_rooms()
        key = thread_key(msg)
        env = {
            **self.env,
            "DESK_ROOM_ID": msg.room_id,
            "DESK_THREAD_ID": msg.thread_root,
        }
        await self.typing(msg.room_id, True)
        try:
            answer = await brain.think(
                self.prompt(msg),
                system=self.system_prompt(),
                tools=self.role.tools,
                cwd=self.workdir,
                env=env,
                session_id=self.state.sessions.get(key),
            )
        finally:
            await self.typing(msg.room_id, False)
        if answer.session_id:
            self.state.sessions[key] = answer.session_id
            self.state.save(self.state_file)
        text = answer.text.strip()
        if answer.is_error:
            log.error("Claude failed: %s", text[:500])
            text = f"I hit an error and stopped: {text[:600]}"
        if not text or text == NO_REPLY:
            log.info("Nothing to say for %s", key)
            return
        await self.agent.reply(msg.room_id, text[:MAX_POST], msg.thread_root)
        log.info("Replied in %s (%d chars)", self.room_name(msg.room_id), len(text))

    async def typing(self, room_id: str, on: bool) -> None:
        try:
            await self.agent.http.post(
                f"/agents/{self.agent.agent_id}/typing",
                headers=self.agent.auth,
                json={"room_id": room_id, "is_typing": on},
            )
        except Exception:  # noqa: BLE001 - a typing hint is never worth failing over
            pass

    async def work(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            getter = asyncio.create_task(self.queue.get())
            stopper = asyncio.create_task(stop.wait())
            done, _ = await asyncio.wait({getter, stopper}, return_when=asyncio.FIRST_COMPLETED)
            stopper.cancel()
            if getter not in done:
                getter.cancel()
                return
            msg = getter.result()
            try:
                await self.handle(msg)
            except Exception as exc:  # noqa: BLE001 - one bad turn must not stop the agent
                log.exception("Turn failed")
                try:
                    await self.agent.reply(msg.room_id, f"That failed on my side: {exc}", msg.thread_root)
                except Exception:  # noqa: BLE001
                    pass

    async def run(self, stop: asyncio.Event) -> None:
        listener = asyncio.create_task(self.agent.listen(self.on_message, stop))
        worker = asyncio.create_task(self.work(stop))
        await asyncio.wait({listener, worker}, return_when=asyncio.FIRST_COMPLETED)
        stop.set()
        await asyncio.gather(listener, worker, return_exceptions=True)
