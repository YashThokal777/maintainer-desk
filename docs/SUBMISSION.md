# Submission form answers (draft: edit after your real run)

Form: https://www.wemakedevs.org/hackathons/switch/submit

**Project title**
Maintainer Desk: AI teammates that triage and review your GitHub repo, with a human yes on every change

**Tracks**
Best Business Workflow (also tick Best Personal or Creative Workflow only if you want; the business track is the fit)

**Project description** (what problem, who it's for)
Open source and product teams lose hours a week to first-pass triage: labelling issues, asking for repro steps, finding duplicates, and running a PR's tests before anyone reviews it. Maintainer Desk is a Switch room group where AI agents do that first pass in the team's own chat. Humans keep every decision: nothing changes on GitHub until a maintainer says yes to the exact command an agent proposes. It's for maintainers of busy repositories and for any engineering team that triages in Slack, Discord, Teams or Mattermost.

**GitHub repository**
https://github.com/YashThokal777/maintainer-desk

**Demo video**
<YouTube/Loom link, under 3 minutes, unlisted>

**How did you use Switch?**
- Agents: three custom agents I wrote on the Switch agent protocol. desk-watcher (Python) polls GitHub and posts every new issue and PR. desk-triager and desk-reviewer have Claude Code as their brain: each chat thread is one headless `claude -p` session, resumed on the next message, with a tool allow-list (read, gh, git, python). All three register via POST /agents and hold the WebSocket connection with ping/pong and a position. The two Claude agents listen with filter=all, so a bare "yes" in their thread reaches them. They reply in threads with the connect_to_room + post_message operations, and they open each other's addressing to "anyone" with update_agent_detail (Switch lets an agent change another agent with the same owner, never itself).
- Platforms: <the one you used: Discord / Mattermost / Slack>. The same rooms work on any Switch bridge.
- Switch features: a version 1 room-group template creates three rooms (intake, review, release) and puts the agents in them (agent pickers in the form), with room instructions, two exclusive roles (triage-lead, first-reviewer), two room links and a kickoff per room. That makes the whole desk one click to reproduce. Addressing is set to "anyone", so every maintainer can direct the agents. The triager hands PRs to the review room with a small `desk-post` command.
- Real work: desk-watcher posts each new GitHub issue and PR into intake. The triager classifies it, searches for duplicates, reproduces bugs and proposes labels plus the exact gh command. A maintainer replies yes, and it runs. PRs go to the reviewer, which checks them out, runs the tests and drafts a review with file:line findings. A maintainer approves before it is posted. In the demo, the reviewer caught a bug the PR's own tests missed.

**What did you like about Switch, and what would you improve?**
Liked: <fill in from experience; examples below, keep only what's true>
- Templates are the killer feature: rooms, roles, links and kickoffs in one YAML made the whole workflow reproducible.
- Any brain can join: the agent protocol is just a WebSocket and a few HTTP calls, so I put headless Claude Code behind it in a few hundred lines of Python.
- The protocol docs are precise (frame types, cursors, takeover semantics) and the loadtest client is a great reference.
Improve:
- Console on Windows can't run agent sessions (they need a POSIX SSH host), and a server Console runs on your own computer only allows agents on that computer, so I couldn't use Console-managed agents at all. <keep if you agree>
- A first-party Python client SDK for the agent protocol, so custom agents don't re-implement the socket loop.
- Posting into a specific thread from POST /message, so a bot can keep each GitHub item in its own thread.
- Mentioning a role (@triage-lead) directly from a custom agent.

**Track details (optional)**
- Blog post: <link to docs/BLOG.md published on Hashnode/dev.to/Medium>
- Wispr usage card: <screenshot from Wispr Flow > Insights > Your usage > Share>
- #HowISwitch post: <link>
