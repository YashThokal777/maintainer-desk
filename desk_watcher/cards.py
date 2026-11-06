"""The messages desk-watcher posts into the room."""

from __future__ import annotations

from .github import Item

EXCERPT = 300


def excerpt(text: str, limit: int = EXCERPT) -> str:
    flat = " ".join(text.split())
    if len(flat) <= limit:
        return flat
    return flat[: limit - 1].rstrip() + "…"


def item_card(item: Item, triager: str) -> str:
    """One new issue or PR, addressed to the triager so it starts work."""
    if item.kind == "pr":
        size = ""
        if item.additions is not None and item.deletions is not None:
            files = item.changed_files or 0
            size = f" · +{item.additions} −{item.deletions} in {files} file{'s' if files != 1 else ''}"
        base = f" · into `{item.base}`" if item.base else ""
        draft = " · draft" if item.draft else ""
        head = f"New PR #{item.number}: **{item.title}** by @{item.author}{size}{base}{draft}"
        ask = "Summarise it, then hand it to the reviewer."
    else:
        labels = ", ".join(item.labels) if item.labels else "none"
        head = f"New issue #{item.number}: **{item.title}** by @{item.author} · labels: {labels}"
        ask = "Triage it: type, labels, next step, and the gh command you propose."
    lines = [f"@{triager} {head}", item.url]
    if item.body.strip():
        lines.append("> " + excerpt(item.body))
    lines.append(ask)
    return "\n".join(lines)


def status_card(
    repo: str, open_items: list[Item], untriaged: list[Item], posted: int, paused: bool
) -> str:
    issues = sum(1 for i in open_items if i.kind == "issue")
    prs = sum(1 for i in open_items if i.kind == "pr")
    lines = [
        f"Watching **{repo}**{' (paused)' if paused else ''}: "
        f"{issues} open issue{'s' if issues != 1 else ''}, {prs} open PR{'s' if prs != 1 else ''}. "
        f"Posted {posted} item{'s' if posted != 1 else ''} to the desk so far."
    ]
    if untriaged:
        oldest = sorted(untriaged, key=lambda i: i.created_at)[:5]
        lines.append(f"{len(untriaged)} issue(s) have no label and no reply yet. Oldest:")
        lines += [f"- #{i.number} {i.title} ({i.age_days}d old) {i.url}" for i in oldest]
    else:
        lines.append("Every open issue has a label or a reply.")
    return "\n".join(lines)


HELP = """I'm desk-watcher. I post every new issue and pull request in {repo} here and mention @{triager}.
Ask me:
- `status`: what's open, and which issues nobody has touched
- `check`: look at GitHub right now instead of waiting
- `pause` / `resume`: stop or restart posting new items
- `help`: this message"""
