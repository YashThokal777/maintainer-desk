"""Create a small public demo repository for the Maintainer Desk, with gh.

    python demo/seed_demo_repo.py backlog <owner>/<name>   # repo + 3 open issues
    python demo/seed_demo_repo.py live <owner>/<name>      # during the demo: 1 issue + 1 PR

`backlog` gives the triager something to sort at kickoff. `live` is what you
run on camera: a new bug report and a pull request arrive, desk-watcher posts
them, and the agents take it from there. The PR fixes the bug but has a
mistake the reviewer should catch (an empty list still crashes).
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

LIB = '''\
"""tinystats: tiny statistics helpers."""


def mean(values):
    """The arithmetic mean of a list of numbers."""
    return sum(values) / len(values)


def median(values):
    """The middle value of a list of numbers."""
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2
'''

TESTS = '''\
from tinystats import mean, median


def test_mean():
    assert mean([1, 2, 3]) == 2


def test_median_odd():
    assert median([3, 1, 2]) == 2


def test_median_even():
    assert median([4, 1, 3, 2]) == 2.5
'''

README = """# tinystats

Tiny statistics helpers. A demo repository, maintained by people and AI agents with the Maintainer Desk on Switch.

```bash
pip install pytest && pytest
```
"""

BACKLOG = [
    ("Add a mode() function", "It would be great to have `mode(values)` returning the most common value."),
    ("README doesn't say which Python versions are supported", "I tried on 3.8 and wasn't sure if that's expected to work."),
    ("How do I compute a weighted mean?", "Is there a way to pass weights to `mean()`? Or should I do it myself?"),
]

LIVE_ISSUE = (
    "mean() crashes with ZeroDivisionError on an empty list",
    "```python\n>>> from tinystats import mean\n>>> mean([])\nZeroDivisionError: division by zero\n```\n"
    "I'd expect it to raise a clear ValueError instead (statistics.mean does that).",
)

# Fixes mean([]) but forgets median([]), which still raises IndexError.
FIX = LIB.replace(
    '    return sum(values) / len(values)',
    '    if not values:\n        raise ValueError("mean() of an empty list")\n    return sum(values) / len(values)',
)


def run(*args: str, cwd: Path | None = None) -> str:
    print("$", " ".join(args))
    out = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"Failed ({out.returncode}): {out.stderr.strip() or out.stdout.strip()}")
    return out.stdout.strip()


def default_branch(repo: str) -> str | None:
    """The repo's default branch; "" when it is empty, None when it doesn't exist."""
    out = subprocess.run(["gh", "repo", "view", repo, "--json", "defaultBranchRef",
                          "--jq", ".defaultBranchRef.name"], capture_output=True, text=True)
    return out.stdout.strip() if out.returncode == 0 else None


def backlog(repo: str) -> None:
    branch = default_branch(repo)
    if branch is None:
        run("gh", "repo", "create", repo, "--public",
            "--description", "Demo repo for the Maintainer Desk (Switch hackathon)")
    if not branch:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "tinystats"
            root.mkdir()
            (root / "tinystats.py").write_text(LIB, encoding="utf-8")
            (root / "test_tinystats.py").write_text(TESTS, encoding="utf-8")
            (root / "README.md").write_text(README, encoding="utf-8")
            run("git", "init", "-q", "-b", "main", cwd=root)
            run("git", "add", ".", cwd=root)
            run("git", "commit", "-q", "-m", "tinystats: mean and median", cwd=root)
            run("git", "remote", "add", "origin", f"https://github.com/{repo}.git", cwd=root)
            run("git", "push", "-q", "-u", "origin", "main", cwd=root)
    else:
        print(f"{repo} already has code on {branch}; adding labels and issues only.")
    for name, color in (("bug", "d73a4a"), ("enhancement", "a2eeef"), ("question", "d876e3"),
                        ("documentation", "0075ca"), ("good first issue", "7057ff")):
        subprocess.run(["gh", "label", "create", name, "--repo", repo, "--color", color, "--force"],
                       capture_output=True)
    for title, body in BACKLOG:
        run("gh", "issue", "create", "--repo", repo, "--title", title, "--body", body)
    print(f"\nDone: https://github.com/{repo} has 3 open issues for the kickoff backlog.")


def live(repo: str) -> None:
    title, body = LIVE_ISSUE
    # Rerunnable: reuse the issue if an earlier run already opened it.
    existing = run("gh", "issue", "list", "--repo", repo, "--state", "open", "--search",
                   f'"{title}" in:title', "--json", "number", "--jq", ".[0].number")
    if existing.strip():
        number = existing.strip()
        print(f"Issue #{number} is already open; reusing it.")
    else:
        issue_url = run("gh", "issue", "create", "--repo", repo, "--title", title, "--body", body)
        number = issue_url.rstrip("/").rsplit("/", 1)[-1]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "tinystats"
        # HTTPS with gh's stored credentials: no SSH keys or host-key prompts.
        helper = "credential.helper=!gh auth git-credential"
        run("git", "-c", helper, "clone", "-q", f"https://github.com/{repo}.git", str(root))
        run("git", "config", "credential.helper", "!gh auth git-credential", cwd=root)
        branch = f"fix-empty-mean-{number}"  # new name per run, so reruns never clash
        run("git", "checkout", "-q", "-b", branch, cwd=root)
        (root / "tinystats.py").write_text(FIX, encoding="utf-8")
        with (root / "test_tinystats.py").open("a", encoding="utf-8") as f:
            f.write(textwrap.dedent('''

                def test_mean_empty():
                    import pytest
                    with pytest.raises(ValueError):
                        mean([])
            '''))
        run("git", "commit", "-q", "-am", f"Raise ValueError for mean() of an empty list (#{number})", cwd=root)
        run("git", "push", "-q", "-u", "origin", branch, cwd=root)
        run("gh", "pr", "create", "--repo", repo, "--head", branch, "--base", "main",
            "--title", "Raise ValueError for empty input",
            "--body", f"Fixes #{number}. `mean([])` now raises a clear ValueError, with a test.", cwd=root)
    print("\nDone: one new issue and one PR. desk-watcher posts them on its next poll (or say `@desk-watcher check`).")


def main() -> int:
    if len(sys.argv) != 3 or sys.argv[1] not in ("backlog", "live") or "/" not in sys.argv[2]:
        print(__doc__)
        return 2
    {"backlog": backlog, "live": live}[sys.argv[1]](sys.argv[2])
    return 0


if __name__ == "__main__":
    sys.exit(main())
