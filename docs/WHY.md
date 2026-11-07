# Why I built Maintainer Desk

## The inbox nobody talks about

Picture the people judging this hackathon on a Monday morning.

Before they write a line of code, there's a queue. New issues from people they've never met. Pull requests from first-time contributors, from bots, from someone who fixed a typo and someone who rewrote a module. Each one asks the same quiet question: *will you look at me?*

I looked up how big that queue really is. In one week, from October 30 to November 6, 2026, the Switch repository got 415 new pull requests. VS Code got 1,488 new issues and pull requests in the same week. CPython got 572. These aren't neglected projects. They're some of the best-run repositories in the world, and the queue still never stops.

And this week, the queue for Switch's maintainers gets longer for a reason they chose themselves. Flip the Switch has a track for core contributions, so some hackathon builders are sending pull requests to Switch itself. The people who will judge my project are the same people reviewing a flood of hackathon PRs, on top of their normal week.

That's why I picked this problem. I didn't want to build a demo about a problem I imagined. I wanted to build for the exact work the people reading this are doing right now.

## The first hour of every maintainer's day

Talk to any maintainer and they'll describe the same first hour:

- Open the issue. Is it a bug, a question or a feature request?
- Ask for repro steps, because nobody included them.
- Try to reproduce it yourself.
- Search for duplicates, because someone reported this last month.
- Pick the labels.
- Open the pull request, check out the branch and run the tests before even starting a real review.

None of that is the interesting part of maintaining software. The interesting part is the decision: should this land, is this the right fix, is this the direction we want? But the decision sits behind an hour of mechanical work, every single day.

So the question I asked was simple: what if that first hour was already done when the maintainer walked in?

## Why not just a bot?

The obvious answer is a GitHub bot that labels and comments automatically. I didn't want that, and it took me a while to say why.

A bot that comments on its own speaks for the project. If it labels a real bug as "question", or tells a first-time contributor their PR is a duplicate when it isn't, a human has to clean up after it in public. Maintainers are protective of their projects for good reason, and an agent that acts alone asks them to give up the one thing they care about most: the final say.

So I flipped it around. The agents do all the legwork, and the decision stays with people. Every change starts as a proposal, written as the exact `gh` command the agent wants to run. A maintainer reads it in the team chat and answers yes, no, or with an edited version. Only a yes, in that exact thread, lets anything reach GitHub. The agents never merge. That stays with the people.

## Why Switch

That idea only works if the agents live where the team already talks. Maintainers don't want another dashboard. They're already in Slack, Discord, Teams or Mattermost all day.

That's exactly what Switch does. It turns a chat channel into a room where agents join as teammates, with roles, instructions and links to other rooms. So Maintainer Desk became three rooms:

- **Intake**, where every new issue and PR lands and the triager sorts it.
- **Review**, where the reviewer checks out each PR, runs the tests and drafts a review.
- **Release**, where merged work collects and release notes get drafted.

The whole desk is one Switch template, so another team can create the same rooms, roles and kickoffs from one form instead of rebuilding them by hand.

## The moment it proved itself

I knew the idea worked during the live demo.

I opened a pull request on a small test library. It fixed a crash: `mean([])` divided by zero on an empty list. It came with a test. The reviewer checked out the branch and ran the suite: four tests, all passing. At that point, a tired maintainer at the end of a long day approves it.

The reviewer didn't stop there. It read the change against the rest of the file and found that `median([])` had the same empty-list hole and still crashed. The PR's own tests couldn't catch it, because they only tested the function the PR touched.

That is the job. Not replacing the maintainer's judgement, but doing the boring "what else has this problem?" check every time, so the human starts from a better place.

## What I learned building it

I didn't get here in a straight line. My first plan was to let Switch Console run the agents for me. On Windows that hit a wall: Console's agent sessions need a POSIX SSH host, and a server Console runs on your own computer only allows agents on that computer. So I wrote the agents myself on Switch's agent protocol. Each one is a small Python process that holds a WebSocket and runs Claude Code headless, one session per chat thread.

That detour taught me the most important design rule of the project: **one GitHub item, one thread, one yes.** When a teammate's first "yes" landed in the channel instead of the thread, the triager correctly ignored it. A yes only counts where the proposal is.

I also learned where the project was still young. During the demo run, the approval gate was a rule the agents followed, written into their instructions and every room's instructions. On the last day I moved it into code. The agents can now only read GitHub, and the desk process runs a proposed command itself, only after it sees a person's plain yes in the right thread. What's left is a read-only GitHub token for the agents' sessions, because they still run Python to reproduce bugs and run tests.

## Why it matters

Open source runs on the time of a small number of people. Every hour they spend sorting and re-running tests is an hour they don't spend on design, on mentoring contributors, or on rest.

Maintainer Desk doesn't ask them to trust an AI with their project. It asks them to say one word, in the chat they already use, after the work is already done.

That's why I built it, and why I built it for this hackathon. The people reviewing it know this inbox better than anyone.
