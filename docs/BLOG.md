# I gave my GitHub repo an AI triage team that can't do anything without my yes

*Building Maintainer Desk on Switch, for the Flip the Switch hackathon. A first-timer's walkthrough.*

> Draft. Replace every `<…>` with what really happened in your run, and add 3–4 screenshots: the template form, the intake card, the triager's proposal with your "yes", and the reviewer's finding. Best Blog is judged on clarity, accuracy and how much it helps a first-time Switch user, so keep the steps exact.

## The problem

Every busy repository has the same first hour of the day: read new issues, ask for repro steps, label them, spot duplicates, check out PRs and run the tests before a real review. It's valuable work, and almost all of it is mechanical.

I didn't want a bot that comments on GitHub by itself. I wanted teammates who do the legwork in the chat where my team already talks, and who wait for a person before they touch anything.

## What Switch is, in one paragraph

[Switch](https://github.com/sandbox-quantum/switch) is open source infrastructure that puts AI agents into team chat. Each channel in Slack, Discord, Teams or Mattermost becomes a **room**. Agents join rooms like teammates, with their own name and avatar. A room holds shared **instructions**, **roles** (named jobs an agent can take up), documents and **links** to other rooms. Switch Console, the desktop app, runs coding agents like Claude Code, Codex and OpenCode on your machine. Any other agent can join through the **agent protocol**: a WebSocket down, HTTP up.

## The design

Three rooms and three custom agents. desk-watcher is plain Python. The triager and the reviewer are Claude Code behind the agent protocol:

- `desk-intake`: desk-watcher posts each new issue or PR and mentions the triager.
- `desk-review`: the triager hands PRs to the reviewer, which runs the tests and drafts a review.
- `desk-release`: merged work, and release notes on request.

The one rule, written into every agent's and every room's instructions: **propose the exact `gh` command, then wait for a human yes.**

## Step 1: run Switch locally

<Your real steps. Mine: installed Switch Console for <OS>, started Docker Desktop, chose "Set up a server on this computer", picked Claude Code for switch-buddy. Time it took: <…>. Gotchas: <…>.>

Switch ships with Mattermost when you self-host, so you don't need admin rights on a company Slack to build or record anything.

## Step 2: the whole desk is one template

A Switch template is a YAML document that says what to create. Switch Console turns its `params:` into a form. Mine creates the three rooms with their instructions and roles, puts the three desk agents in them, links the rooms, and posts a kickoff in each:

```yaml
params:
  repo:    { type: string, label: GitHub repository }
  triager: { type: agent, label: Triager, default: [desk-triager] }
rooms:
  - name: "{team}-intake"
    agents: ["{watcher}", "{triager}"]
    instructions: |
      ... Nothing changes on GitHub without a maintainer's yes ...
    roles:
      - name: triage-lead
        exclusive: true
    kickoff: |
      @{triager} read the open issues with gh and post a numbered backlog ...
links:
  - { from: "{team}-intake", to: "{team}-review", label: pull requests go to review }
```

Things I learned:
- **Agents only start working when a message addresses them.** That's what `kickoff:` is for: mention them, or they sit in the room quietly.
- `type: agent` params turn into agent pickers in the form, so the template works with agents you already registered.
- You can lint a template with Switch's own linter (`switch_core.template_lint.lint_template`) before you paste it into Console.

## Why my agents are custom, not Console-managed

I first had Console run Claude Code for the triager and reviewer. On Windows that hit two walls: Console's agent sessions need a POSIX SSH host ("SDK sessions require a POSIX SSH execution host"), and a server Console runs on your own computer only lets agents run on that same computer. I tried WSL as an SSH host and got stuck on both rules.

So I put Claude Code behind the agent protocol myself. Each agent is a small Python process that holds the Switch socket. When a message is for it, it runs `claude -p` with the role's instructions and a tool allow-list (read, `gh`, `git`, `python`), and posts the answer as a thread reply. Each chat thread is one Claude session, resumed with `--resume` on the next message, so when a maintainer replies "yes" the agent still knows exactly which command it proposed.

## Step 3: a custom agent on the agent protocol

All three agents share one small client, `desk_watcher/switch.py`. The protocol in practice:

1. **Register once** with a registration key: `POST /agents` returns an `id` and an `api_key`. The key is shown once, so save it. (On a local Windows server started by Console, the key is `AGENT_REGISTRATION_TOKEN` in `%APPDATA%\switchdash\local-switch-server\native\run\switch-core.env`.)
2. **Open the WebSocket** at `/agents/{id}/connection/ws?connection_id=<uuid>&scope=all&filter=addressed&protocol=9`. Reuse the same connection id on every reconnect.
3. **Answer every `ping`** with `{"type": "pong", "cursor": n}`. That's the heartbeat. Miss it and the connection lapses.
4. **Pick a filter.** With `filter=addressed` you only get messages meant for you. The triager and reviewer use `filter=all`, so a bare "yes" in their thread reaches them, and they decide for themselves whether it's theirs.
5. **Post** with `POST /agents/{id}/message` and `{room_id, content}`. That has no thread field, so for thread replies call the `connect_to_room` operation, then `post_message` with a `thread_id`.
6. **Open addressing.** New agents only take direction from their owner, and an agent can't change its own setting. Agents with the same owner can change each other's, so `python -m desk_agents open-addressing` has each one set the next to `anyone` through `update_agent_detail`.

```python
if event == "ping":
    await ws.send(json.dumps({"type": "pong", "cursor": self.cursor, "position": self.position}))
```

<What tripped you up, if anything.>

## Step 4: the demo

<Describe your real run: the backlog the triager produced at kickoff, the live issue and PR, the triager's proposed command, your teammate's "yes", the reviewer catching that `median([])` still crashes even though the PR's tests passed, the review posted after approval.>

## What I'd tell a first-time Switch user

- Start with the 10-minute quickstart and switch-buddy before writing any YAML.
- Read `examples/` in the repo. `support-desk` and `red-blue-workroom` taught me more than any page.
- Put your rules in room instructions as well as agent instructions. Every agent in the room reads them.
- Set addressing to `anyone` for agents your whole team should talk to. If a teammate's message gets "You're not permitted to direct messages to me", that's the setting.
- An agent you build yourself can have any brain. Mine is `claude -p`, one session per thread.

## Links

- Code: https://github.com/YashThokal777/maintainer-desk
- Demo video: https://youtu.be/9JXPkAAXD48
- Switch: https://github.com/sandbox-quantum/switch · docs: https://docs.switchagents.ai

#HowISwitch
