# FAQ

**1. What stops the triager from labelling or closing something without permission?**

Today the gate lives in the instructions. Every agent, and every room, carries the same rule: read GitHub freely, change nothing until a person in the thread has said a clear yes ("yes", "approve", "go", "apply") to the exact command the agent proposed. The agents never merge, never close PRs and never delete. The tool allow-list (read, `gh`, `git`, `python` and a few others) limits the blast radius: anything outside it is refused in headless mode. But `gh` is on the list, so the allow-list alone doesn't block a GitHub write. The yes is a rule the model follows, not a check the code enforces.

If someone says "ok sure", it isn't one of the listed yes words, so the agent has to judge it. I haven't tested that case. In the demo, a "yes" sent to the channel instead of the thread was correctly ignored. The next step is to make the gate deterministic: the agent writes its proposed command to a file, and a small wrapper runs it only after code sees an approved reply in that thread.

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

The deterministic approval gate from answer 1, because it turns the core promise ("nothing reaches GitHub without a yes") from a rule into a guarantee. After that, a GitHub webhook instead of polling, and posting new commits on a PR into the thread where it was already reviewed.

**8. One thing to ask the Switch team**

Let `POST /agents/{id}/message` post into a specific thread. My whole approval flow is one GitHub item, one thread, one yes, and today I need the `connect_to_room` + `post_message` operations over the socket to reply in a thread. A thread field on the REST call would make that simple for any custom agent, and a first-party Python SDK for the protocol would save every builder the socket loop I had to write.
