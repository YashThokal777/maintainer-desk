"""Settings, all from environment variables (a `.env` file is read too)."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


def load_dotenv(path: Path) -> None:
    """Read KEY=value lines into the environment, without overriding it."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def github_token_from_gh() -> str | None:
    """The token `gh` is signed in with, so no separate token is needed."""
    if not shutil.which("gh"):
        return None
    try:
        out = subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return None
    token = out.stdout.strip()
    return token or None


@dataclass(frozen=True)
class Settings:
    api_url: str
    registration_key: str | None
    repo: str
    team: str
    agent_name: str
    intake_room: str
    triager: str
    poll_seconds: int
    state_file: Path
    github_token: str | None
    announce_existing: bool

    @property
    def ws_url(self) -> str:
        return self.api_url.replace("https://", "wss://", 1).replace(
            "http://", "ws://", 1
        )

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> "Settings":
        load_dotenv(env_file or Path(".env"))
        repo = os.environ.get("DESK_REPO", "").strip()
        if "/" not in repo:
            raise SystemExit("Set DESK_REPO to the GitHub repository, as owner/name.")
        team = os.environ.get("DESK_TEAM", "desk").strip()
        return cls(
            api_url=os.environ.get("SWITCH_API_URL", "http://localhost:8000").rstrip("/"),
            registration_key=os.environ.get("SWITCH_REGISTRATION_KEY") or None,
            repo=repo,
            team=team,
            agent_name=os.environ.get("DESK_AGENT_NAME", "desk-watcher"),
            intake_room=os.environ.get("DESK_INTAKE_ROOM", f"{team}-intake"),
            triager=os.environ.get("DESK_TRIAGER", f"{team}-triager"),
            poll_seconds=max(15, int(os.environ.get("DESK_POLL_SECONDS", "60"))),
            state_file=Path(os.environ.get("DESK_STATE_FILE", ".desk-state.json")),
            github_token=os.environ.get("GITHUB_TOKEN") or github_token_from_gh(),
            announce_existing=os.environ.get("DESK_ANNOUNCE_EXISTING", "").lower()
            in ("1", "true", "yes"),
        )
