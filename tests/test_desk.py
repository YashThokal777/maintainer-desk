"""The desk end to end against fakes: GitHub over httpx.MockTransport, Switch
over a real local WebSocket server speaking the agent protocol's frames."""

import asyncio
import json
from pathlib import Path

import httpx
import websockets

from desk_watcher.config import Settings
from desk_watcher.desk import Desk
from desk_watcher.github import GitHub
from desk_watcher.state import State
from desk_watcher.switch import Agent

ROOMS = [{"room_id": "r-intake", "name": "desk-intake"}, {"room_id": "r-review", "name": "desk-review"}]


def gh_issue(n, pr=False, title=None):
    raw = {
        "number": n,
        "title": title or f"Thing {n}",
        "user": {"login": "bob"},
        "html_url": f"https://github.com/o/r/{'pull' if pr else 'issues'}/{n}",
        "body": f"Body of {n}",
        "labels": [],
        "comments": 0,
        "created_at": "2026-11-01T10:00:00Z",
    }
    if pr:
        raw["pull_request"] = {}
    return raw


class FakeWorld:
    """GitHub and Switch's HTTP side, as one MockTransport."""

    def __init__(self):
        self.issues = [gh_issue(1), gh_issue(2)]
        self.posts: list[dict] = []
        self.ops: list[tuple[str, dict]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.url.host == "api.github.com":
            if path == "/repos/o/r/issues":
                return httpx.Response(200, json=self.issues)
            if path.startswith("/repos/o/r/pulls/"):
                return httpx.Response(
                    200,
                    json={"additions": 10, "deletions": 2, "changed_files": 1, "base": {"ref": "main"}},
                )
            return httpx.Response(404)
        if path.endswith("/message"):
            self.posts.append(json.loads(request.content))
            return httpx.Response(200, json={"ok": True, "event_id": "e"})
        if "/ops/" in path:
            name = path.rsplit("/", 1)[-1]
            self.ops.append((name, json.loads(request.content or b"{}")))
            if name == "list_rooms":
                return httpx.Response(200, json={"result": ROOMS})
            return httpx.Response(200, json={"result": {"ok": True}})
        return httpx.Response(404)


def settings(tmp_path: Path, port: int = 1) -> Settings:
    return Settings(
        api_url=f"http://127.0.0.1:{port}",
        registration_key=None,
        repo="o/r",
        team="desk",
        agent_name="desk-watcher",
        intake_room="desk-intake",
        triager="desk-triager",
        poll_seconds=15,
        state_file=tmp_path / "state.json",
        github_token=None,
        announce_existing=False,
    )


def make_desk(tmp_path, world, port=1):
    s = settings(tmp_path, port)
    transport = httpx.MockTransport(world.handler)
    http = httpx.AsyncClient(base_url=s.api_url, transport=transport)
    gh = GitHub("o/r", client=httpx.AsyncClient(base_url="https://api.github.com", transport=transport))
    state = State(agent_id="a1", api_key="k1")
    agent = Agent(http, s.ws_url, "a1", "k1", state.connection_id)
    return Desk(s, state, agent, gh)


def test_first_run_marks_backlog_seen_then_posts_only_new_items(tmp_path):
    async def go():
        world = FakeWorld()
        desk = make_desk(tmp_path, world)
        assert await desk.poll_once() == []  # backlog: the triager reads it at kickoff
        assert world.posts == []

        world.issues.insert(0, gh_issue(3, pr=True, title="Fix empty input"))
        world.issues.insert(0, gh_issue(4))
        posted = await desk.poll_once()
        assert [i.number for i in posted] == [3, 4]
        assert [p["room_id"] for p in world.posts] == ["r-intake", "r-intake"]
        assert world.posts[0]["content"].startswith("@desk-triager New PR #3: **Fix empty input**")
        assert "+10 −2 in 1 file" in world.posts[0]["content"]

        assert await desk.poll_once() == []  # nothing new, nothing posted twice
        saved = State.load(desk.settings.state_file)
        assert saved.seen_for("o/r") == {1, 2, 3, 4} and saved.posted == 2

    asyncio.run(go())


def test_pause_holds_new_items_until_resume(tmp_path):
    async def go():
        world = FakeWorld()
        desk = make_desk(tmp_path, world)
        await desk.poll_once()
        desk.paused = True
        world.issues.insert(0, gh_issue(5))
        assert await desk.poll_once() == []
        desk.paused = False
        assert [i.number for i in await desk.poll_once()] == [5]

    asyncio.run(go())


def test_socket_answers_pings_and_runs_addressed_commands(tmp_path):
    """A fake Switch socket: connection_state, a ping, then a maintainer
    asking for status. The watcher must pong with its cursor and reply."""

    async def go():
        world = FakeWorld()
        received: list[dict] = []
        opened_with: list[str] = []

        async def fake_switch(ws):
            opened_with.append(ws.request.path)
            await ws.send(json.dumps({"event": "connection_state", "data": {"rooms": ["r-intake"], "generation": 3}}))
            await ws.send(json.dumps({"event": "ping", "data": {}}))
            received.append(json.loads(await ws.recv()))
            await ws.send(json.dumps({
                "event": "message", "id": 41,
                "data": {"type": "message", "room_id": "r-intake", "sequence": 41,
                         "payload": {"addressed": True, "sender": "@switch-user-x:localhost",
                                     "sender_name": "priya", "body": "@desk-watcher status"}},
            }))
            await ws.send(json.dumps({"event": "ping", "data": {}}))
            received.append(json.loads(await ws.recv()))
            await ws.wait_closed()  # hold the socket open until the client leaves

        async with websockets.serve(fake_switch, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            desk = make_desk(tmp_path, world, port)
            stop = asyncio.Event()
            task = asyncio.create_task(desk.agent.listen(desk.on_message, stop))
            for _ in range(100):
                if len(received) == 2 and world.posts:
                    break
                await asyncio.sleep(0.05)
            stop.set()
            await asyncio.wait_for(task, 5)

        path = opened_with[0]
        assert path.startswith("/agents/a1/connection/ws?")
        assert "filter=addressed" in path and "scope=all" in path and "protocol=9" in path
        assert received[0] == {"type": "pong", "cursor": 0, "position": {}}
        assert received[1]["cursor"] == 41  # the message moved the cursor
        assert desk.agent.generation == 3
        assert world.posts and world.posts[0]["room_id"] == "r-intake"
        assert world.posts[0]["content"].startswith("Watching **o/r**")

    asyncio.run(go())
