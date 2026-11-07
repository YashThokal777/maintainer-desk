# Maintainer Desk

[![tests](https://github.com/YashThokal777/maintainer-desk/actions/workflows/tests.yml/badge.svg)](https://github.com/YashThokal777/maintainer-desk/actions/workflows/tests.yml)

**An open source maintainer team where AI agents do the first pass and people make every call, in the chat you already use.**

Built on [Switch](https://github.com/sandbox-quantum/switch) for the *Flip the Switch* hackathon (Track 1: Best Business Workflow).

> Maintainers drown in notifications. In one week (Oct 30 – Nov 6, 2026) the Switch repo got 415 new pull requests. Maintainer Desk turns a GitHub repository into three chat rooms where a triager agent and a reviewer agent sort issues, reproduce bugs, run the tests on every PR and draft the review. The humans in the room answer **yes**, **no** or with an edit. Nothing touches GitHub without that yes.

**Demo video (2:29):** https://youtu.be/9JXPkAAXD48

---

## What happens

1. Someone opens an issue or a PR on GitHub.
2. **desk-watcher**, a custom agent on the Switch agent protocol, posts it into `#desk-intake` and mentions the triager.
3. **Triager**, a custom Switch agent with Claude Code as its brain, reads it with `gh`, searches for duplicates, reproduces bugs, and replies in the thread with a type, labels, next step and **the exact `gh` command it proposes**.
4. A maintainer replies `yes` in that thread. Only then does the triager run that command.
5. Pull requests are handed to **Reviewer** in `#desk-review`. It checks out the PR, runs the tests and posts a verdict, findings with `file:line`, and a draft review.
6. A maintainer approves the draft and the reviewer posts it to GitHub. Agents never merge. People do.
7. Merged work is summarised in `#desk-release`, and `@desk-triager release notes` drafts the changelog.

**See it on GitHub.** These are what the agents posted during the recorded demo run, each one after a maintainer said yes in the thread:
- [The triager's comment on tinystats issue #7](https://github.com/YashThokal777/tinystats/issues/7#issuecomment-6690062461): reproduced at `tinystats.py:6`, flagged the same gap in `median([])`, and labelled the issue `bug` and `good first issue`.
- [The reviewer's review on tinystats PR #8](https://github.com/YashThokal777/tinystats/pull/8#pullrequestreview-5803709451): 4 tests passed, and `median([])` still crashes, which the PR's own tests missed.

```mermaid
flowchart LR
  GH[("GitHub repo")] -- new issue / PR --> W["desk-watcher<br/>custom agent, agent protocol"]
  subgraph S["Switch room group"]
    direction LR
    I["desk-intake<br/>watcher · triager · maintainers"]
    R["desk-review<br/>triager · reviewer · maintainers"]
    L["desk-release<br/>triager · reviewer · maintainers"]
    I -- "link: PRs go to review" --> R
    R -- "link: merged work goes to release" --> L
  end
  W -- posts card, @mentions triager --> I
  T["desk-triager<br/>custom agent + claude -p"] <--> I
  T -- "desk-post: hands PR over" --> R
  V["desk-reviewer<br/>custom agent + claude -p"] <--> R
  M(("Maintainers<br/>Discord / Slack / Mattermost")) <--> I & R & L
  T -. "gh, only after a human yes" .-> GH
  V -. "gh pr review, only after a human yes" .-> GH
```

## Why Switch is the whole project

Take Switch out and nothing is left. Every piece below is a Switch feature:

| Switch feature | How the desk uses it |
|---|---|
| **Room group template** ([`templates/maintainer-desk.template.yaml`](templates/maintainer-desk.template.yaml)) | One form in Switch Console creates all three rooms, puts the three agents in them, and sets the instructions, roles and links. Then it posts a kickoff in each room. That makes the desk reproducible in one click. |
| **The agent protocol** ([`desk_watcher/switch.py`](desk_watcher/switch.py)) | All three agents are custom agents. Each registers through `POST /agents` and holds a WebSocket at `/agents/{id}/connection/ws` (answering `ping` with `pong` + position). They reply in threads with the `connect_to_room` + `post_message` operations. desk-watcher listens with `filter=addressed`. The triager and reviewer use `filter=all`, so they see the whole room and decide for themselves when a bare "yes" is meant for them. |
| **Claude Code behind the protocol** ([`desk_agents/`](desk_agents/)) | Each chat thread is one headless `claude -p` session, resumed on the next message in that thread. Tools are an allow-list (read, `gh`, `git`, `python`), so the brain can't wander. `desk-post` lets an agent post to another room, which is how the triager hands a PR to the reviewer. |
| **Addressing** | `python -m desk_agents open-addressing` sets every desk agent to `anyone`, so every maintainer in the room can direct them, not only their owner. Switch only lets an agent's owner change this, never the agent itself. The desk agents share an owner, so each one opens up the others through the `update_agent_detail` operation. |
| **Room instructions and roles** | Each room carries the desk's rules, including the human gate. The `triage-lead` and `first-reviewer` roles are exclusive, so you can swap the agent behind a job without anyone re-announcing it. |
| **Linked rooms** | `intake → review → release`. The agents know where each kind of work goes next. |
| **Collaboration bridges** | The same rooms show up in Discord, Slack, Teams or Mattermost. Maintainers never open another tool. |
| **Kickoff** | Creating the desk sets it working at once: the triager posts a triaged backlog of the open issues, and the reviewer lists the open PRs. |

## The human gate

Every agent follows the same rule, set in its instructions and in each room's instructions:

> Read GitHub freely. Change nothing on GitHub (labels, comments, reviews, closing) until a person in the room has said yes to that exact action. Never merge.

The agents propose the exact command (`gh issue edit 12 --add-label bug`), so the yes is specific. The allow-list adds a second layer: in headless mode any tool outside it is refused, not asked about.

---

## Run it yourself

### What you need

- [Switch Console](https://github.com/sandbox-quantum/switch/releases/latest) (macOS, Windows, Linux) and Docker Desktop, running.
- [Claude Code](https://claude.com/claude-code), signed in on your machine. The triager and reviewer run it headless (`claude -p`).
- The [GitHub CLI](https://cli.github.com) signed in (`gh auth login`). The agents use it, and desk-watcher reads its token.
- Python 3.10+.

### 1. Start Switch (about 10 minutes)

Follow the [Switch quickstart](https://docs.switchagents.ai/switch-rooms/getting-started). In Switch Console, choose **Set up a server on this computer**. It starts Switch in Docker with Mattermost included, so you need no Slack admin rights. To use Discord or Slack instead, see [Connect messaging apps](https://docs.switchagents.ai/switch-rooms/deploy/messaging-apps/index).

### 2. Make a repo for the desk to look after

Use your own repository, or create the demo one:

```bash
python demo/seed_demo_repo.py backlog <your-github-user>/tinystats
```

That creates a small Python library with tests, standard labels and three open issues.

### 3. Register the three agents (once)

```bash
pip install -e .
cp .env.example .env        # set SWITCH_API_URL, DESK_REPO and SWITCH_REGISTRATION_KEY
python -m desk_watcher register
python -m desk_agents register triager
python -m desk_agents register reviewer
python -m desk_agents open-addressing   # let every maintainer address them
```

Each agent's key is saved in a `.desk-state*.json` file, which git ignores.

> **Local server started by Switch Console on Windows?** It runs natively, not in Docker, on a port Console picks. Its settings are in `%APPDATA%\switchdash\local-switch-server\native\run\switch-core.env`. Set `SWITCH_API_URL=http://127.0.0.1:<SERVER_PORT>`. `desk_agents` reads that file's `AGENT_REGISTRATION_TOKEN` itself when `SWITCH_REGISTRATION_KEY` is unset.

### 4. Start them

Each one is a long-running process. Use three terminals:

```bash
python -m desk_watcher run
python -m desk_agents run triager
python -m desk_agents run reviewer
```

The triager and reviewer each clone the repository into `~/.maintainer-desk/<agent>/` and work there.

### 5. Create the desk

In Switch Console, open the **Templates** page and import [`templates/maintainer-desk.template.yaml`](templates/maintainer-desk.template.yaml). Click **Use**, fill in the repository (the three agents are picked by default), then **Create**. You get three linked rooms with the agents in them, and a kickoff in each room that the agents answer straight away.

Then invite your teammates into the three rooms from your chat app.

Open a new issue or PR on the repository, or run `python demo/seed_demo_repo.py live <owner>/tinystats`. It appears in `#desk-intake` within a minute. To skip the wait, say `@desk-watcher check`.

> **Why custom agents and not Console-managed ones?** A server Console runs on your own computer only lets agents run on that computer, and on Windows Console can't run agent sessions at all ("SDK sessions require a POSIX SSH execution host"). The desk's agents speak the agent protocol directly, so they run anywhere Python and Claude Code do.

### Talking to the desk

| Say | Who answers |
|---|---|
| `yes` / `no` / an edited command, in a thread | Triager or reviewer: runs it, skips it, or runs your version |
| `@desk-triager backlog` | Numbered list of triaged items and their state |
| `@desk-triager release notes` | Draft notes from merged PRs, grouped and credited |
| `@desk-reviewer review #14` | A review of any PR, on request |
| `@desk-watcher status` | Open counts, plus the oldest issues nobody has touched |
| `@desk-watcher check` / `pause` / `resume` / `help` | Controls the watcher |

## Project layout

```
templates/maintainer-desk.template.yaml   the desk: rooms, agents in them, roles, links, kickoffs
desk_agents/                              the triager and reviewer: custom agents with a Claude Code brain
  roles.py       their instructions, the human gate, and the tool allow-list
  teammate.py    who to answer (mention, or a person in a thread it's working), one session per thread
  brain.py       runs `claude -p`, resumes the thread's session
  __main__.py    register / run / open-addressing, and `desk-post`
desk_watcher/                             custom Switch agent (Python, agent protocol)
  switch.py      register, WebSocket listen loop with ping/pong + reconnect, ops, threaded replies
  desk.py        poll GitHub, post new items, answer commands
  github.py      GitHub REST reads
  cards.py       the messages it posts
  commands.py    parses what people ask it
demo/seed_demo_repo.py                    creates the demo repo, backlog and live PR
tests/                                    pytest, including a fake Switch WebSocket server
docs/                                     demo script, blog post, submission notes
```

## Tests

```bash
pip install -e ".[dev]" && pytest
```

The tests cover the cards, command parsing, GitHub diffing, pause and resume, when a teammate answers (and when it stays quiet), threaded replies and session resume, reading Claude's output, and the protocol loop. That last test runs against a local WebSocket server that sends `connection_state`, `ping` and an addressed `message` frame. It checks that the watcher opens the socket with the right parameters, pongs with its cursor and answers in the room. The template passes Switch's own template linter (`switch_core.template_lint`) and its room-group schema with no warnings.

## What's next

- Post GitHub events into the thread they belong to: a new commit on a PR the reviewer already reviewed goes to that PR's thread.
- Use a GitHub webhook instead of polling.
- A `security` role in the review room, held by a dedicated agent for PRs that touch auth or dependencies.

## License

MIT
