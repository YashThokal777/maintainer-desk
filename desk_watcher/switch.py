"""A small client for the Switch agent protocol.

Down: one WebSocket at /agents/{id}/connection/ws carrying JSON frames
`{"event", "data", "id"}`. The server sends `ping` frames and the client
answers `{"type": "pong", "cursor": n}`, which is the heartbeat.
Up: plain HTTP. Messages go to POST /agents/{id}/message, and everything else
is an operation at POST /agents/{id}/ops/{name} with the arguments unwrapped.

See https://docs.switchagents.ai/switch-rooms/internals/agent-protocol
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from urllib.parse import urlencode

import httpx
import websockets

log = logging.getLogger("desk_watcher.switch")

PROTOCOL = 9
OWN_EVENTS = "s"

PROFILE = {
    # desk-watcher is a long-running process that polls GitHub, so it is
    # reachable whether or not anyone is talking to it.
    "connection_model": "always_on",
    "message_exchange": True,
    "pre_invocation_mediation": [],
    "post_invocation_mediation": [],
    "event_reporting": [],
    "task_protocol": {"can_delegate": False, "can_accept": False},
}


class SwitchError(RuntimeError):
    pass


def _detail(r: httpx.Response) -> str:
    try:
        return json.dumps(r.json())[:300]
    except ValueError:
        return r.text[:300]


async def register(
    http: httpx.AsyncClient, registration_key: str, name: str, description: str
) -> tuple[str, str]:
    """Register the agent once. Returns (agent_id, api_key); the key is shown once."""
    r = await http.post(
        "/agents",
        headers={"Authorization": f"Bearer {registration_key}"},
        json={
            "name": name,
            "description": description,
            "connector_type": "custom",
            "integration_profile": PROFILE,
        },
    )
    if r.status_code == 409:
        raise SwitchError(
            f"An agent named {name!r} already exists. Delete it in the Gateway, "
            "or set DESK_AGENT_NAME to another name."
        )
    if r.status_code != 200:
        raise SwitchError(f"Registration failed ({r.status_code}): {_detail(r)}")
    body = r.json()
    return body["id"], body["api_key"]


@dataclass
class Message:
    room_id: str
    sender: str
    sender_name: str
    body: str
    addressed: bool
    thread_id: str | None = None
    message_id: str = ""
    # "user" (a person on a bridge), "agent" or "platform" (Switch itself,
    # e.g. a template's kickoff).
    sender_kind: str | None = None
    # The person's role in the room's workspace ("owner", "admin", "member");
    # None for agents, the platform, or a person no Switch user has claimed.
    sender_role: str | None = None

    @property
    def thread_root(self) -> str:
        """The thread this message belongs to; a top-level message starts one."""
        return self.thread_id or self.message_id


Handler = Callable[[Message], Awaitable[None]]


def furthest(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in b.items():
        if isinstance(v, int) and v > out.get(k, -1):
            out[k] = v
    return out


@dataclass
class Agent:
    """One registered agent: its HTTP calls and its event socket."""

    http: httpx.AsyncClient
    ws_url: str
    agent_id: str
    api_key: str
    connection_id: str
    client_name: str = "maintainer-desk"
    # "addressed": only messages that address this agent. "all": every message
    # in its rooms, so the agent can follow threads and decide for itself.
    delivery_filter: str = "addressed"
    position: dict[str, int] = field(default_factory=dict)
    generation: int | None = None
    connected: asyncio.Event = field(default_factory=asyncio.Event)
    _post_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    @property
    def cursor(self) -> int:
        return self.position.get(OWN_EVENTS, 0)

    # ── HTTP up ─────────────────────────────────────────────────────────

    async def op(self, name: str, **args: object) -> object:
        # The connection header binds a call to the socket's room; the server
        # refuses it (409) while no socket is open, so send it only then.
        headers = dict(self.auth)
        if self.connected.is_set():
            headers["X-Switch-Connection-Id"] = self.connection_id
        r = await self.http.post(f"/agents/{self.agent_id}/ops/{name}", headers=headers, json=args)
        if r.status_code != 200:
            raise SwitchError(f"{name} failed ({r.status_code}): {_detail(r)}")
        return r.json().get("result")

    async def post(self, room_id: str, content: str) -> None:
        r = await self.http.post(
            f"/agents/{self.agent_id}/message",
            headers=self.auth,
            json={"room_id": room_id, "content": content},
        )
        if r.status_code != 200:
            raise SwitchError(f"Posting failed ({r.status_code}): {_detail(r)}")

    async def reply(self, room_id: str, body: str, thread_id: str | None = None) -> None:
        """Post into a room, as a threaded reply when `thread_id` is given.

        Plain POST /message can't thread, so a reply goes through the
        `connect_to_room` + `post_message` operations, which need the socket.
        """
        if not thread_id or not self.connected.is_set():
            await self.post(room_id, body)
            return
        async with self._post_lock:
            await self.op("connect_to_room", room_id=room_id, include_general_instructions=False)
            await self.op("post_message", body=body, thread_id=thread_id)

    async def rooms(self) -> list[dict]:
        result = await self.op("list_rooms")
        return list(result) if isinstance(result, list) else []

    # ── WebSocket down ──────────────────────────────────────────────────

    def socket_url(self) -> str:
        params = {
            "connection_id": self.connection_id,
            "scope": "all",
            "filter": self.delivery_filter,
            "start_from": str(self.cursor) if self.cursor else "head",
            "start_at": json.dumps(self.position) if self.position else "head",
            "protocol": str(PROTOCOL),
            "protocol_accepts": "1",
            "client": self.client_name,
            "client_version": "0.1.0",
        }
        if self.generation is not None:
            params["expected_generation"] = str(self.generation)
        return f"{self.ws_url}/agents/{self.agent_id}/connection/ws?{urlencode(params)}"

    async def listen(self, on_message: Handler, stop: asyncio.Event) -> None:
        """Keep the socket open until `stop` is set, reconnecting with backoff."""
        backoff = 1.0
        while not stop.is_set():
            why = "closed"
            try:
                async with websockets.connect(
                    self.socket_url(),
                    additional_headers=self.auth,
                    open_timeout=30,
                    max_size=None,
                    ping_interval=None,  # the server's ping frames are the heartbeat
                ) as ws:
                    backoff = 1.0
                    why = await self._read(ws, on_message, stop)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - every drop is retried
                why = f"{type(exc).__name__}: {exc}"
            self.connected.clear()
            if why == "taken_over":
                log.error("Another process took over this connection id; stopping.")
                return
            if stop.is_set():
                return
            log.warning("Socket ended (%s); reconnecting in %.0fs", why, backoff)
            try:
                await asyncio.wait_for(stop.wait(), backoff)
            except TimeoutError:
                pass
            backoff = min(backoff * 2, 30)

    async def _read(self, ws, on_message: Handler, stop: asyncio.Event) -> str:
        stopper = asyncio.create_task(stop.wait())
        try:
            while True:
                recv = asyncio.create_task(ws.recv())
                done, _ = await asyncio.wait(
                    {recv, stopper}, return_when=asyncio.FIRST_COMPLETED
                )
                if stopper in done:
                    recv.cancel()
                    await ws.close()
                    return "stopped"
                frame = json.loads(recv.result())
                ended = await self._frame(ws, frame, on_message)
                if ended:
                    return ended
        finally:
            stopper.cancel()

    async def _frame(self, ws, frame: dict, on_message: Handler) -> str | None:
        event = frame.get("event")
        data = frame.get("data") or {}
        if event == "ping":
            await ws.send(
                json.dumps({"type": "pong", "cursor": self.cursor, "position": self.position})
            )
            return None
        if event == "refused":
            detail = data.get("detail")
            code = detail.get("code") if isinstance(detail, dict) else None
            log.error("Connection refused: %s", data)
            return "taken_over" if code == "taken_over" else f"refused {data.get('status')}"
        if event == "connection_state":
            self.generation = data.get("generation", self.generation)
            if isinstance(data.get("position"), dict):
                self.position = furthest(self.position, data["position"])
            if not self.connected.is_set():
                log.info("Connected to Switch; rooms: %s", data.get("rooms"))
            self.connected.set()
            return None
        if event == "evicted":
            return str(data.get("code") or data.get("reason") or "evicted")
        if event == "gap":
            if isinstance(data.get("resumed_position"), dict):
                self.position = data["resumed_position"]
            return None

        if isinstance(data.get("position"), dict):
            self.position = furthest(self.position, data["position"])
        elif frame.get("id") is not None:
            self.position = furthest(self.position, {OWN_EVENTS: int(frame["id"])})

        if event == "message":
            payload = data.get("payload") or {}
            addressed = bool(payload.get("addressed"))
            if addressed or self.delivery_filter == "all":
                await on_message(
                    Message(
                        room_id=data.get("room_id", ""),
                        sender=payload.get("sender", ""),
                        sender_name=payload.get("sender_name", ""),
                        body=payload.get("body", ""),
                        addressed=addressed,
                        thread_id=payload.get("thread_id"),
                        message_id=payload.get("message_id", ""),
                        sender_kind=payload.get("sender_kind"),
                        sender_role=payload.get("sender_role"),
                    )
                )
        return None
