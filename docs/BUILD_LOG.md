# Build log

The key decisions behind Maintainer Desk, in the order they were made. Built solo with Claude Code on Nov 6–7, 2026 (times IST).

**1. Scope for one person (Nov 6, 2:30–3:45 PM).** The first idea needed a team, so I picked a workflow one engineer could build and demo in a day and a half: first-pass triage and review for a GitHub repo. It is real, repetitive work, and the Switch repo alone got 415 PRs in a week.

**2. Self-hosted Mattermost (4:50 PM).** Switch Console's "set up a server on this computer" runs Mattermost in Docker. No workspace admin rights needed, and anyone can reproduce the setup.

**3. From Console-managed agents to the agent protocol (4:51–6:06 PM).** The plan was for Console to run Claude Code as the triager and reviewer. On Windows that failed twice over: Console's agent sessions need a POSIX SSH host ("SDK sessions require a POSIX SSH execution host"), and a server Console runs on your own computer only lets agents run on that same computer. Using WSL as the SSH host hit both limits. So I wrote the agents myself on the Switch agent protocol: a small Python process per agent holds the WebSocket and runs headless `claude -p` with a tool allow-list. This also made the agents portable, since they run anywhere Python and Claude Code do.

**4. One GitHub item, one thread, one yes.** Each chat thread is one Claude session, resumed with `--resume`, so a later "yes" maps to the exact command the agent proposed. `POST /agents/{id}/message` can't reply in a thread, so replies go through the `connect_to_room` + `post_message` operations. The triager and reviewer listen with `filter=all` so a bare "yes" reaches them, and a yes only counts in the thread of its proposal. In the demo a "yes" sent to the channel was correctly ignored.

**5. Let every maintainer direct the agents.** New agents only take direction from their owner, and an agent can't change its own addressing. Agents with the same owner can change each other's, so `open-addressing` sets each one to `anyone` with `update_agent_detail`.

**6. The whole desk is one template.** Three linked rooms (intake, review, release), the agents in them, room instructions carrying the human gate, two exclusive roles and a kickoff per room. Checked with Switch's own template linter.

**7. A seeded demo repo.** `demo/seed_demo_repo.py` creates `tinystats` with a bug report (#7) and a fixing PR (#8), using a fresh fix branch each run, so the run is repeatable on camera.

**8. Live run, with two surprises (Nov 6, evening).** GitHub doesn't let you approve or request changes on your own PR, so the reviewer offered a plain review comment instead, and posted it after a second yes. The reviewer's first run also stopped on a Claude usage limit and was re-run once the limit reset. It still caught a bug the PR's tests missed: `median([])` crashes.

**9. Demo video.** A 2:29 motion-graphics cut built with HyperFrames, with AI narration (Kokoro TTS) and a CC0 music track.

**10. Final polish by voice (Nov 7).** The docs fixes, CI, GitHub proof links and demo-run measurements were done by dictating to Claude Code with Wispr Flow.
