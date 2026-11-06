"""What the watcher remembers between runs, in one JSON file.

The agent's API key is returned once, at registration, so it lives here.
Keep the file out of git (it is in .gitignore).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class State:
    agent_id: str | None = None
    api_key: str | None = None
    # Reused on every reconnect, so the connection survives a dropped socket.
    connection_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    # Issue and PR numbers already posted (or deliberately skipped), per repo.
    seen: dict[str, list[int]] = field(default_factory=dict)
    posted: int = 0

    @classmethod
    def load(cls, path: Path) -> "State":
        if not path.is_file():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)

    def save(self, path: Path) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        tmp.replace(path)

    def seen_for(self, repo: str) -> set[int]:
        return set(self.seen.get(repo, []))

    def mark_seen(self, repo: str, numbers: set[int]) -> None:
        merged = self.seen_for(repo) | numbers
        # Keep the file small: the newest 500 numbers are plenty.
        self.seen[repo] = sorted(merged)[-500:]

    def is_first_run(self, repo: str) -> bool:
        return repo not in self.seen
