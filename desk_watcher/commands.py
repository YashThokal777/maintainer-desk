"""Turns a message addressed to desk-watcher into one of its commands."""

from __future__ import annotations

import re

MENTION = re.compile(r"(?<!\w)@[\w.\-]+")

COMMANDS = {
    "help": "help",
    "status": "status",
    "digest": "status",
    "check": "check",
    "check now": "check",
    "refresh": "check",
    "pause": "pause",
    "stop": "pause",
    "resume": "resume",
    "start": "resume",
}


def parse(body: str) -> str:
    """The command a message asks for, or "help" when it asks for none we know."""
    text = MENTION.sub(" ", body).lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = " ".join(text.split())
    if text in COMMANDS:
        return COMMANDS[text]
    # Longest phrase first, so "check now" wins over "check".
    for phrase in sorted(COMMANDS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(phrase)}\b", text):
            return COMMANDS[phrase]
    return "help"
