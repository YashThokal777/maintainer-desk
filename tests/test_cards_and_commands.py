from datetime import datetime, timedelta, timezone

import pytest

from desk_watcher import cards, commands
from desk_watcher.github import Item, new_items, untriaged


def item(number, kind="issue", **kw):
    base = dict(
        number=number,
        kind=kind,
        title=f"Item {number}",
        author="alice",
        url=f"https://github.com/o/r/issues/{number}",
        body="",
        labels=(),
        comments=0,
        created_at=datetime.now(timezone.utc) - timedelta(days=number),
    )
    base.update(kw)
    return Item(**base)


def test_issue_card_mentions_triager_and_asks_for_triage():
    card = cards.item_card(item(7, body="It crashes   when\n\nthe input is empty"), "desk-triager")
    first = card.splitlines()[0]
    assert first.startswith("@desk-triager New issue #7")
    assert "labels: none" in first
    assert "> It crashes when the input is empty" in card
    assert "gh command" in card


def test_pr_card_shows_size_and_base():
    pr = item(9, kind="pr", additions=12, deletions=3, changed_files=1, base="main", draft=True)
    card = cards.item_card(pr, "desk-triager")
    assert "New PR #9" in card
    assert "+12 −3 in 1 file " in card + " "
    assert "into `main`" in card
    assert "draft" in card
    assert "hand it to the reviewer" in card


def test_excerpt_truncates_long_bodies():
    text = "word " * 200
    out = cards.excerpt(text, 50)
    assert len(out) <= 50 and out.endswith("…")


def test_new_items_are_unseen_and_oldest_first():
    items = [item(3), item(1), item(2)]
    assert [i.number for i in new_items(items, {2})] == [1, 3]


def test_untriaged_skips_prs_labelled_and_answered():
    items = [item(1), item(2, labels=("bug",)), item(3, comments=1), item(4, kind="pr")]
    assert [i.number for i in untriaged(items)] == [1]


def test_status_card_lists_oldest_untriaged():
    items = [item(1), item(5), item(2, kind="pr")]
    card = cards.status_card("o/r", items, untriaged(items), posted=4, paused=False)
    assert "2 open issues, 1 open PR" in card
    assert card.index("#5") < card.index("#1")  # oldest first


@pytest.mark.parametrize(
    "body, expected",
    [
        ("@desk-watcher status", "status"),
        ("@desk-watcher STATUS please", "status"),
        ("@desk-watcher check now!", "check"),
        ("hey @desk-watcher can you pause for a bit", "pause"),
        ("@desk-watcher resume", "resume"),
        ("@desk-watcher digest", "status"),
        ("@desk-watcher what can you do?", "help"),
        ("@desk-watcher", "help"),
        # A mention of another agent is not a command word.
        ("@desk-watcher ask @desk-checker", "help"),
    ],
)
def test_parse(body, expected):
    assert commands.parse(body) == expected
