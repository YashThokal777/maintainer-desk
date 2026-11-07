# Submission

Submitted to [Flip the Switch](https://www.wemakedevs.org/hackathons/switch) on Nov 7, 2026 as a solo entry. These are the answers as filed.

**Project title**
Maintainer Desk: AI teammates that triage and review your GitHub repo, with a human yes on every change

**Track**
Best Business Workflow

**Project description**
Open source and product teams lose hours a week to first-pass triage: labelling issues, asking for repro steps, finding duplicates, and running a PR's tests before anyone reviews it. In one week (Oct 30 – Nov 6, 2026) Switch's own repo got 415 new pull requests. Maintainer Desk is a Switch room group where AI agents do that first pass in the team's own chat. Humans keep every decision: nothing changes on GitHub until a maintainer says yes to the exact command an agent proposes. It's for maintainers of busy repositories and for any engineering team that triages in Slack, Discord, Teams or Mattermost.

**Links**
- Repository: https://github.com/YashThokal777/maintainer-desk
- Demo video: https://youtu.be/GFWQGjrnIP0
- Blog post: https://dev.to/yash_thokal_a1899d36b0351/i-gave-my-github-repo-an-ai-triage-team-that-cant-do-anything-without-my-yes-1h6n
- #HowISwitch post: https://www.linkedin.com/feed/update/urn:li:activity:7524555203140960257/

**How did you use Switch?**

Agents: three custom agents I wrote on the Switch agent protocol. desk-watcher (Python) polls GitHub and posts every new issue and PR. desk-triager and desk-reviewer use Claude Code as their brain: each chat thread is one headless `claude -p` session, resumed on the next message, with a tool allow-list (read, gh, git, python). All three register via POST /agents and hold the WebSocket connection with ping/pong. The two Claude agents listen with filter=all, so a bare "yes" in their thread reaches them. They reply in threads with connect_to_room + post_message, and open each other's addressing to "anyone" with update_agent_detail.

Platform: Mattermost. The same rooms work on any Switch bridge.

Switch features: a room-group template creates three rooms (intake, review, release) and puts the agents in them, with room instructions, two exclusive roles (triage-lead, first-reviewer), two room links and a kickoff per room, so the whole desk is one click to reproduce. Addressing is set to "anyone", so every maintainer can direct the agents.

Real work: desk-watcher posts each new GitHub issue and PR into intake. The triager reproduces bugs, checks for duplicates and proposes labels plus the exact gh command; a maintainer replies yes in the thread and only then does it run. PRs go to the reviewer, which checks them out, runs the tests and drafts a review with file:line findings, posted only after another yes. In the demo, the reviewer caught a bug the PR's own tests missed: median([]) still crashes.

**What did you like about Switch, and what would you improve?**

Liked:
- Templates are the killer feature: rooms, roles, links and kickoffs in one YAML made the whole workflow reproducible.
- Any brain can join: the agent protocol is a WebSocket and a few HTTP calls, so I put headless Claude Code behind it in a few hundred lines of Python.
- Thread-aware messaging makes a human approval gate natural: one GitHub item, one thread, one yes.

Improve:
- On Windows, Console can't run agent sessions (they need a POSIX SSH host), so I had to write custom agents instead of using Console-managed ones.
- A first-party Python SDK for the agent protocol, so custom agents don't re-implement the socket loop.
- Posting into a specific thread from POST /message, so a bot can keep each GitHub item in its own thread.
- When an agent is offline, its queued messages get an "I'm currently offline" auto-reply; a quieter option would keep busy rooms clean.
