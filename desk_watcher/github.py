"""Reads a repository's open issues and pull requests from the GitHub REST API."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

import httpx

API = "https://api.github.com"


@dataclass(frozen=True)
class Item:
    number: int
    kind: str  # "issue" or "pr"
    title: str
    author: str
    url: str
    body: str
    labels: tuple[str, ...]
    comments: int
    created_at: datetime
    # Pull requests only.
    additions: int | None = None
    deletions: int | None = None
    changed_files: int | None = None
    base: str | None = None
    draft: bool = False

    @property
    def age_days(self) -> int:
        return (datetime.now(timezone.utc) - self.created_at).days


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _item(raw: dict) -> Item:
    return Item(
        number=raw["number"],
        kind="pr" if "pull_request" in raw else "issue",
        title=raw.get("title") or "",
        author=(raw.get("user") or {}).get("login", "unknown"),
        url=raw.get("html_url", ""),
        body=raw.get("body") or "",
        labels=tuple(lbl["name"] for lbl in raw.get("labels", []) if "name" in lbl),
        comments=raw.get("comments", 0),
        created_at=_parse_time(raw["created_at"]),
        draft=bool(raw.get("draft", False)),
    )


@dataclass
class GitHub:
    repo: str
    token: str | None = None
    client: httpx.AsyncClient | None = None
    _own_client: bool = field(default=False, init=False)

    async def __aenter__(self) -> "GitHub":
        if self.client is None:
            headers = {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "maintainer-desk",
            }
            if self.token:
                headers["Authorization"] = f"Bearer {self.token}"
            self.client = httpx.AsyncClient(base_url=API, headers=headers, timeout=30)
            self._own_client = True
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._own_client and self.client is not None:
            await self.client.aclose()

    async def open_items(self, limit: int = 50) -> list[Item]:
        """Open issues and PRs, newest first. The issues endpoint lists both."""
        assert self.client is not None
        r = await self.client.get(
            f"/repos/{self.repo}/issues",
            params={
                "state": "open",
                "sort": "created",
                "direction": "desc",
                "per_page": min(limit, 100),
            },
        )
        r.raise_for_status()
        return [_item(raw) for raw in r.json()]

    async def with_pr_details(self, item: Item) -> Item:
        """Add size and base branch to a PR; an issue is returned unchanged."""
        if item.kind != "pr":
            return item
        assert self.client is not None
        r = await self.client.get(f"/repos/{self.repo}/pulls/{item.number}")
        if r.status_code != 200:
            return item
        pr = r.json()
        return replace(
            item,
            additions=pr.get("additions"),
            deletions=pr.get("deletions"),
            changed_files=pr.get("changed_files"),
            base=(pr.get("base") or {}).get("ref"),
            draft=bool(pr.get("draft", item.draft)),
        )


def new_items(items: list[Item], seen: set[int]) -> list[Item]:
    """Items not posted yet, oldest first so the room reads in order."""
    return sorted((i for i in items if i.number not in seen), key=lambda i: i.number)


def untriaged(items: list[Item]) -> list[Item]:
    """Open issues nobody has labelled or answered yet."""
    return [i for i in items if i.kind == "issue" and not i.labels and i.comments == 0]
