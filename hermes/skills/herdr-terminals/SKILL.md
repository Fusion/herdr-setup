---
name: herdr-terminals
description: "Use inside Herdr (HC_TERMINAL_ID is set) to talk to other agents and terminals with hc: send a message to another agent (Claude, Codex, another Hermes), read its screen, answer a message that came as <hc from=...>, start a program or agent in a new terminal, wait for one to finish."
version: 1.0.0
author: shepherdr local
metadata:
  hermes:
    tags: [herdr, hc, terminals, agents, messaging]
---

# Talking to other terminals with hc (Herdr)

You run in a Herdr terminal (your address is `$HC_TERMINAL_ID`, e.g. `t3q`). Other agents and
programs run in terminals of their own. Use the `terminal` tool to run `hc`:

| want | command |
|---|---|
| list terminals (address, program, status) | `hc ls` |
| one terminal's details (`--json` for status) | `hc get t5` |
| send an agent a message (paste + Enter) | `hc send t5 "Rebase on main, then tell me"` |
| read its screen and history | `hc read t5` |
| press keys | `hc keys t5 enter` / `esc` / `ctrl+c` |
| stop its current turn | `hc interrupt t5` |
| wait until it stops working (never sleep) | `hc wait t5` |
| start a program/agent in the background | `hc run --bg claude` (prints JSON with `address`) |

## Rules
- Send with a literal message: `hc send t5 "words"`, one `hc send` per message. The chat shows it
  as "you → t5: words" only when the text is written out in the command, not built in a variable.
- A message from another agent reaches you as `<hc from="t5 name">text</hc>`. Answer it with
  `hc send t5 "..."`; your reply in your own chat does not reach it.
- `hc send` refuses a terminal that is busy; wait (`hc wait t5`) and send again, or add `--force`
  only when it must interrupt.
- Never `hc kill` / `hc rm` a terminal you didn't start unless the person asks.
