import asyncio
import json
from pathlib import Path

import httpx

from desk_agents import brain
from desk_agents.roles import ROLES, TRIAGER
from desk_agents.teammate import Teammate, TeammateState, mentions
from desk_watcher.switch import Agent, Message


def msg(body, *, sender="u1", name="priya", kind="user", thread=None, mid="m1", room="r1", addressed=False):
    return Message(room_id=room, sender=sender, sender_name=name, body=body, addressed=addressed,
                   thread_id=thread, message_id=mid, sender_kind=kind)


class FakeSwitch:
    """Records what the teammate sends to Switch over HTTP."""

    def __init__(self):
        self.calls = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content or b"{}")
        self.calls.append((request.url.path, body))
        if request.url.path.endswith("/ops/list_rooms"):
            return httpx.Response(200, json={"result": [{"room_id": "r1", "name": "desk-intake"}]})
        return httpx.Response(200, json={"ok": True, "result": {}})

    def posts(self):
        return [(p, b) for p, b in self.calls if p.endswith("/ops/post_message") or p.endswith("/message")]


def make_mate(tmp_path: Path, http: httpx.AsyncClient) -> Teammate:
    agent = Agent(http, "ws://x", "agent-1", "key", "conn-1", delivery_filter="all")
    agent.connected.set()
    return Teammate(role=TRIAGER, name="desk-triager", team="desk", repo="o/tinystats", agent=agent,
                    state=TeammateState(agent_id="agent-1", api_key="key"),
                    state_file=tmp_path / "state.json", workdir=tmp_path,
                    peers=("desk-reviewer", "desk-watcher"))


def test_mentions_matches_whole_names_only():
    assert mentions("hey @desk-triager, look", "desk-triager")
    assert mentions("@Desk-Triager backlog", "desk-triager")
    assert not mentions("@desk-triager-2 hi", "desk-triager")
    assert not mentions("email desk-triager@x", "desk-triager")


def test_should_answer_rules(tmp_path):
    mate = make_mate(tmp_path, httpx.AsyncClient(transport=httpx.MockTransport(FakeSwitch())))
    # Mentioned, by a person, the watcher or Switch's kickoff: yes.
    assert mate.should_answer(msg("@desk-triager backlog"))
    assert mate.should_answer(msg("New issue #4 @desk-triager", kind="agent", name="desk-watcher"))
    assert mate.should_answer(msg("@desk-triager introduce yourself", kind="platform"))
    # Its own messages, and chatter not meant for it: no.
    assert not mate.should_answer(msg("@desk-triager hi", sender="agent-1", name="desk-triager"))
    assert not mate.should_answer(msg("lunch?"))
    # Switch's delivery notices mention the agent but ask nothing of it.
    assert not mate.should_answer(msg("⚠️ @desk-triager **desk-reviewer** isn't in this room, so your "
                                      "message won't reach it.", kind="platform", name="admin"))
    # A bare "yes" counts once the agent is working in that thread...
    mate.state.sessions["r1:root"] = "sess"
    assert mate.should_answer(msg("yes", thread="root", mid="m2"))
    # ...but not when it's addressed to the other agent, or comes from an agent.
    assert not mate.should_answer(msg("@desk-reviewer yes", thread="root", mid="m3"))
    assert not mate.should_answer(msg("done", thread="root", kind="agent", name="desk-reviewer"))


def test_parse_output_reads_claude_json():
    out = json.dumps({"type": "result", "subtype": "success", "is_error": False,
                      "result": "**Type:** bug", "session_id": "s-1"})
    a = brain.parse_output(out)
    assert (a.text, a.session_id, a.is_error) == ("**Type:** bug", "s-1", False)
    assert brain.parse_output("not json").is_error
    failed = json.dumps({"type": "result", "subtype": "error_max_turns", "result": "", "session_id": "s"})
    assert brain.parse_output(failed).is_error


def test_claude_argv_resumes_and_limits_tools():
    argv = brain.claude_argv(system="be brief", tools=("Read", "Bash(gh:*)"), session_id="s-9",
                             executable="claude")
    assert argv[:4] == ["claude", "-p", "--output-format", "json"]
    assert argv[argv.index("--allowedTools") + 1] == "Read,Bash(gh:*)"
    assert argv[argv.index("--resume") + 1] == "s-9"
    assert "--resume" not in brain.claude_argv(system="x", tools=(), session_id=None, executable="c")


def test_roles_name_and_gate():
    assert ROLES["reviewer"].name("desk") == "desk-reviewer"
    for role in ROLES.values():
        text = role.instructions.format(name=role.name("desk"), team="desk", repo="o/r")
        assert "Never merge" in text and "NO_REPLY" in text
        assert not any(t.startswith("Bash(rm") or t == "Bash" for t in role.tools)
        # Claude may read GitHub but never write to it: no bare gh, no gh api, no git push.
        assert "Bash(gh:*)" not in role.tools and "Bash(git:*)" not in role.tools
        gh = [t for t in role.tools if t.startswith("Bash(gh ")]
        writes = ("edit", "comment", "review", "merge", "close", "api", "delete", "create")
        assert gh and not any(w in t for t in gh for w in writes)
        assert not any("push" in t for t in role.tools)


def test_handle_threads_reply_and_remembers_session(tmp_path, monkeypatch):
    switch = FakeSwitch()
    seen = {}

    async def fake_think(prompt, *, system, tools, cwd, env, session_id, timeout=0):
        seen.update(prompt=prompt, session_id=session_id, env=env)
        return brain.Answer("**Type:** bug\n**Proposed action:** `gh issue edit 4 --add-label bug`", "sess-1")

    monkeypatch.setattr(brain, "think", fake_think)

    async def go():
        async with httpx.AsyncClient(base_url="http://switch", transport=httpx.MockTransport(switch)) as http:
            mate = make_mate(tmp_path, http)
            await mate.handle(msg("New issue #4 @desk-triager", kind="agent", name="desk-watcher", mid="card"))
            # A follow-up in the thread resumes the same Claude session.
            await mate.handle(msg("is it a dup?", thread="card", mid="m2"))
            return mate

    mate = asyncio.run(go())
    assert "#desk-intake" in seen["prompt"] and "is it a dup?" in seen["prompt"]
    assert seen["session_id"] == "sess-1"
    assert seen["env"]["DESK_THREAD_ID"] == "card"
    assert mate.state.sessions == {"r1:card": "sess-1"}
    assert json.loads((tmp_path / "state.json").read_text())["sessions"] == {"r1:card": "sess-1"}
    posts = switch.posts()
    assert len(posts) == 2
    path, body = posts[0]
    assert path.endswith("/ops/post_message") and body["thread_id"] == "card"
    connects = [b for p, b in switch.calls if p.endswith("/ops/connect_to_room")]
    assert connects and connects[0]["room_id"] == "r1"


def test_handle_stays_quiet_on_no_reply(tmp_path, monkeypatch):
    switch = FakeSwitch()

    async def fake_think(*a, **k):
        return brain.Answer("NO_REPLY", "s")

    monkeypatch.setattr(brain, "think", fake_think)

    async def go():
        async with httpx.AsyncClient(base_url="http://switch", transport=httpx.MockTransport(switch)) as http:
            await make_mate(tmp_path, http).handle(msg("@desk-triager thanks"))

    asyncio.run(go())
    assert switch.posts() == []
