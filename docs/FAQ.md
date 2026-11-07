# FAQ

**1. What stops the triager from labelling or closing something without permission?**

Code. The agents' Claude sessions can only read GitHub: read-only `gh` (view, list, diff, search, checks, checkout) and local `git` with no push. Anything else is refused in headless mode. A GitHub write happens in one place, the desk process itself ([`desk_agents/gate.py`](../desk_agents/gate.py)). The agent ends its reply with a **Proposed action:**, the exact command. The desk stores it for that thread and runs it only when a person (not an agent) answers in the same thread, after the proposal, with a plain yes ("yes", "approve", "go", "apply"). One yes runs one command, once. "no" or "hold" cancels it, and an edit means a new proposal and a fresh yes. Even on a yes, the desk only runs `gh issue edit|comment` and `gh pr edit|comment|review` on its own repo: never merge, close, delete or `gh api`. [`tests/test_gate.py`](../tests/test_gate.py) covers each case.

If someone says "ok sure", it isn't a plain yes, so nothing runs: the message goes to the agent, which can only answer or propose again. In the demo run on Nov 6 the gate was still a rule in the instructions, and a "yes" sent to the channel instead of the thread was correctly ignored. On Nov 7 the gate moved into code, so that case is now a check, not a judgment.

One gap is still open. The agents can run Python, because the triager reproduces bugs and the reviewer runs tests. A model that went looking could call GitHub's API from Python with the signed-in account. The fix is a read-only GitHub token for the agents' sessions, with write access held only by the desk process.

**2. Why team chat instead of a GitHub bot that comments on its own?**

Because the decision belongs to the team, and the team already talks in chat. A bot that comments on its own speaks for the project before a maintainer has looked. In chat, the agent's proposal is a draft: people can say yes, no, or edit the command first. Maintainers also get all the context in one thread (repro, duplicates, test results) without opening five GitHub tabs.

**3. What went wrong with Console-managed agents on Windows, and how did writing your own agents fix it?**

Console's agent sessions need a POSIX SSH host ("SDK sessions require a POSIX SSH execution host"), and a server Console runs on your own computer only lets agents run on that same computer. On Windows I couldn't satisfy both, even with WSL as the SSH host. So I wrote the agents myself on the Switch agent protocol: a small Python process per agent that registers with `POST /agents`, holds the WebSocket and runs headless `claude -p` for each thread. It took a few hundred lines, and now the agents run anywhere Python and Claude Code do.

**4. The moment the reviewer caught the `median([])` bug**

PR #8 fixed `mean([])`, which crashed with `ZeroDivisionError`, and it came with a test. The reviewer checked out the branch and ran the suite: 4 passed. A rushed maintainer would approve at that point. Instead it read the diff against the rest of the module and found that `median([])` has the same empty-input hole and still raises `IndexError`. The PR's own tests couldn't catch that, because they only tested the function the PR touched. That's the value for a maintainer: the agent does the boring "what else has this problem?" check every time.

**5. How would this work on a repo getting 400 PRs a week?**

About 57 PRs a day, plus issues. What would break first:
- **Model limits.** Each item is a Claude session. In the demo the reviewer's first run stopped on a usage limit, so at that volume you need an API plan with headroom, and a queue so one slow review doesn't block the rest.
- **One reviewer.** A single reviewer agent handles every PR. You'd run several behind the `first-reviewer` role.
- **Polling.** desk-watcher polls GitHub (every 60 seconds by default). A webhook would be faster and lighter on the API.
- **Human attention.** At 57 a day, maintainers need batching: "approve all the labels in this list" rather than 57 separate yeses.

**6. What does someone need to run this, and how long does setup take?**

Switch Console with Docker Desktop, Claude Code signed in, the GitHub CLI signed in, and Python 3.10+. Switch, Mattermost and the desk's code are open source. The running cost is Claude usage. Setup is about 10 minutes for Switch, then a few commands to register and start the three agents, then one template form in Console to create the rooms.

**7. If you had one more week, what would you build first?**

A read-only GitHub token for the agents' sessions, so the code gate from answer 1 covers every path to GitHub, not just `gh`. That makes the core promise ("nothing reaches GitHub without a yes") a guarantee end to end. After that, a GitHub webhook instead of polling, and posting new commits on a PR into the thread where it was already reviewed.

**8. One thing to ask the Switch team**

Let `POST /agents/{id}/message` post into a specific thread. My whole approval flow is one GitHub item, one thread, one yes, and today I need the `connect_to_room` + `post_message` operations over the socket to reply in a thread. A thread field on the REST call would make that simple for any custom agent, and a first-party Python SDK for the protocol would save every builder the socket loop I had to write.
