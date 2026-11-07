"""The human gate, enforced in code: nothing reaches GitHub without a yes."""

import asyncio

import httpx
import pytest

from desk_agents import brain, gate
from test_agents import FakeSwitch, make_mate, msg

PROPOSAL = "**Type:** bug\n**Proposed action:**\n```sh\ngh issue edit 4 --add-label bug\n```"
CARD = dict(kind="agent", name="desk-watcher", mid="card")


def test_proposed_command_reads_fenced_and_inline():
    assert gate.proposed_command(PROPOSAL) == "gh issue edit 4 --add-label bug"
    assert gate.proposed_command("**Proposed action:** `gh pr comment 8 --body hi`") == "gh pr comment 8 --body hi"
    body = '**Proposed action:**\n```sh\ngh pr review 8 --comment --body "Use `median([])`\nthanks"\n```'
    assert gate.proposed_command(body).startswith('gh pr review 8 --comment --body "Use `median')
    assert gate.proposed_command("No action needed.") is None


def test_check_allows_only_listed_writes_to_this_repo():
    assert gate.check("gh issue edit 4 --add-label bug", "o/r") == ["gh", "issue", "edit", "4", "--add-label", "bug"]
    assert gate.check('gh pr review 8 --comment --body "two\nlines"', "o/r")[-1] == "two\nlines"
    assert gate.check("gh issue comment 4 -R O/R --body x", "o/r")
    for bad in ("gh pr merge 8", "gh issue close 4", "gh api -X DELETE repos/o/r", "git push",
                "gh issue edit 4 --repo other/repo --add-label bug", "gh issue edit 4 --repo=x/y",
                "gh issue edit 4 --add-label bug\ngh pr merge 8", 'gh issue comment 4 --body "open'):
        with pytest.raises(gate.GateError):
            gate.check(bad, "o/r")


def test_verdict_needs_a_plain_yes():
    for yes in ("yes", "Yes!", "  approve ", "@desk-triager go", "go ahead.", "LGTM 👍"):
        assert gate.verdict(yes, "desk-triager") == "yes", yes
    for no in ("no", "hold", "Not yet."):
        assert gate.verdict(no, "desk-triager") == "no", no
    for other in ("ok sure", "yes but use docs", "yes?? why bug", "@desk-reviewer yes x"):
        assert gate.verdict(other, "desk-triager") is None, other


def run_thread(tmp_path, monkeypatch, *follow_ups, first=PROPOSAL, later="Noted.", queued=False):
    """The watcher posts an issue card, the agent answers `first`, then each follow-up arrives.

    Returns the commands the desk ran, the prompts Claude saw, the texts posted, and the teammate.
    """
    switch, ran, prompts = FakeSwitch(), [], []

    async def fake_think(prompt, **_):
        prompts.append(prompt)
        return brain.Answer(first if len(prompts) == 1 else later, "sess-1")

    async def fake_run(argv, *, cwd, env, timeout=120):
        ran.append(argv)
        return gate.Ran(" ".join(argv), 0, "https://github.com/o/tinystats/issues/4")

    monkeypatch.setattr(brain, "think", fake_think)
    monkeypatch.setattr(gate, "run", fake_run)

    async def go():
        async with httpx.AsyncClient(base_url="http://switch", transport=httpx.MockTransport(switch)) as http:
            mate = make_mate(tmp_path, http)
            mate.state.sessions["r1:card"] = "sess-0"
            card = msg("New issue #4 @desk-triager", **CARD)
            if queued:
                # Everything arrives while the agent is still writing its answer to the card.
                for m in (card, *follow_ups):
                    await mate.on_message(m)
                while not mate.queue.empty():
                    await mate.handle(mate.queue.get_nowait())
            else:
                await mate.handle(card)
                for m in follow_ups:
                    await mate.on_message(m)
                    while not mate.queue.empty():
                        await mate.handle(mate.queue.get_nowait())
            return mate

    mate = asyncio.run(go())
    posts = [b.get("content") or b.get("body") or "" for _, b in switch.posts()]
    return ran, prompts, posts, mate


def test_yes_in_the_thread_runs_the_proposed_command(tmp_path, monkeypatch):
    ran, prompts, posts, mate = run_thread(tmp_path, monkeypatch, msg("yes", thread="card", mid="m2"))
    assert ran == [["gh", "issue", "edit", "4", "--add-label", "bug"]]
    assert len(prompts) == 1  # the yes never reached Claude: the desk ran the command
    assert "on priya's yes" in posts[-1] and "issues/4" in posts[-1]
    assert mate.state.pending == {}  # one yes, one run
    assert "r1:card" in mate.state.ran  # the agent hears what ran on its next turn


def test_nothing_runs_without_a_human_yes_in_that_thread(tmp_path, monkeypatch):
    ran, prompts, _, mate = run_thread(
        tmp_path, monkeypatch,
        msg("@desk-triager yes", mid="m2"),                       # in the channel, not the thread
        msg("@desk-triager yes", thread="other", mid="m3"),       # in another thread
        msg("@desk-triager yes", thread="card", mid="m4", kind="agent", name="desk-reviewer"),
        msg("ok sure", thread="card", mid="m5"),                  # not a plain yes: Claude answers
    )
    assert ran == []
    assert mate.state.pending["r1:card"]["command"] == "gh issue edit 4 --add-label bug"
    assert any("ok sure" in p for p in prompts)


def test_a_no_cancels_the_proposal(tmp_path, monkeypatch):
    ran, _, _, mate = run_thread(tmp_path, monkeypatch, msg("hold", thread="card", mid="m2"),
                                 msg("yes", thread="card", mid="m3"), later="Okay, holding.")
    assert ran == [] and mate.state.pending == {}


def test_an_edited_proposal_needs_a_fresh_yes(tmp_path, monkeypatch):
    edited = "**Proposed action:** `gh issue edit 4 --add-label docs`"
    ran, *_ = run_thread(tmp_path, monkeypatch, msg("use docs instead", thread="card", mid="m2"),
                         msg("yes", thread="card", mid="m3"), later=edited)
    assert ran == [["gh", "issue", "edit", "4", "--add-label", "docs"]]


def test_a_yes_sent_before_the_proposal_does_not_count(tmp_path, monkeypatch):
    # The yes arrives while the agent is still writing the proposal it would approve.
    ran, _, _, mate = run_thread(tmp_path, monkeypatch, msg("yes", thread="card", mid="m2"),
                                 later="Noted.", queued=True)
    assert ran == []
    assert mate.state.pending  # the proposal still waits for a yes written after it


def test_a_proposal_the_desk_wont_run_is_not_stored(tmp_path, monkeypatch):
    merge = "**Proposed action:** `gh pr merge 8 --squash`"
    ran, *_, mate = run_thread(tmp_path, monkeypatch, msg("yes", thread="card", mid="m2"), first=merge)
    assert ran == [] and mate.state.pending == {}


def test_pending_proposals_survive_a_restart(tmp_path, monkeypatch):
    from desk_agents.teammate import TeammateState

    _, _, _, mate = run_thread(tmp_path, monkeypatch)
    again = TeammateState.load(tmp_path / "state.json")
    assert again.pending == mate.state.pending and again.clock == mate.state.clock
