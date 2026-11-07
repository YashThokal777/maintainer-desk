# #HowISwitch post

Posted on LinkedIn on Nov 7, 2026: https://www.linkedin.com/feed/update/urn:li:activity:7524555203140960257/

---

My GitHub repo now has an AI triage team, and it can't touch anything without my yes.

For the Flip the Switch hackathon I built Maintainer Desk on Switch:

→ a custom agent posts every new issue and PR into our team chat
→ a Claude Code triager reproduces the bug, checks for duplicates and proposes labels
→ a reviewer agent checks out each PR, runs the tests and drafts the review
→ a maintainer says "yes" in the thread, and only then does anything reach GitHub

In the demo, the reviewer caught a bug the PR's own tests missed.

The whole desk (3 agents, 3 linked rooms, roles and kickoffs) is one Switch template, so anyone can spin it up in one click.

Demo: https://youtu.be/9JXPkAAXD48
Code: https://github.com/YashThokal777/maintainer-desk
How I built it: https://dev.to/yash_thokal_a1899d36b0351/i-gave-my-github-repo-an-ai-triage-team-that-cant-do-anything-without-my-yes-1h6n

Built with Switch, for the WeMakeDevs hackathon.

#HowISwitch #FlipTheSwitch #AIAgents #OpenSource
