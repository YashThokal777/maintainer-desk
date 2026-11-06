# Demo video: shot list (aim for 2:45)

The form asks for the agent "working in a real chat with your teammates". Have one friend in the rooms as a second maintainer (call them Priya below). Record the chat full screen, with the GitHub tab in a second window.

**Before recording:** desk created from the template, kickoffs already answered, `python -m desk_watcher run` running, demo repo seeded with `backlog`. Close notifications. Zoom the chat to about 125%.

| Time | Show | Say (or dictate with Wispr) |
|---|---|---|
| 0:00–0:15 | The Switch repo's PR count, then the desk in chat | "Maintainers drown in issues and PRs. Switch's own repo got 300 PRs this week. This is Maintainer Desk: AI teammates do the first pass, people make every call, right here in chat." |
| 0:15–0:35 | Switch Console template form, then the three rooms it created with the agents in them | "One Switch template creates three linked rooms, puts a watcher, a triager and a reviewer in them with their rules and roles, then kicks them off. The triager and reviewer are custom agents with Claude Code as their brain." |
| 0:35–0:50 | The kickoff backlog the triager posted in intake | "On kickoff the triager read every open issue and proposed labels. It changed nothing." |
| 0:50–1:10 | Terminal: `python demo/seed_demo_repo.py live …`, then the watcher's cards arriving in intake | "A user reports a crash and opens a fix. desk-watcher, a custom agent on Switch's agent protocol, posts both and mentions the triager." |
| 1:10–1:35 | The triager's reply: type, labels, repro output, proposed `gh` command. **Priya** replies "yes". The triager confirms with a link. GitHub tab shows the label. | "It reproduced the bug and proposed one command. Nothing happens until a human says yes. Priya does, and it's on GitHub." |
| 1:35–2:15 | Review room: the triager hands the PR over. The reviewer checks it out, runs the tests (4 passed) and flags that `median([])` still crashes, with file:line, plus a draft review. | "The reviewer ran the tests. They pass, but it caught what the PR missed: median of an empty list still crashes." |
| 2:15–2:30 | You reply "yes, request changes". The review appears on GitHub. | "I approve the draft, and it's posted to the PR. Agents never merge." |
| 2:30–2:45 | `@desk-triager backlog` answer, then the release room | "Ask the triager for the backlog, or for release notes. Built on Switch: rooms, roles, links, templates and the agent protocol. Thanks!" |

Tips: cut the waiting (agent thinking time) in editing, and caption it "running tests…". Keep each cut under 20 seconds. Upload as unlisted on YouTube.
