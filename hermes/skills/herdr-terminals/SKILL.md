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
| read its screen and history | `hc read t5` (screen only; `--lines 5000` adds scrollback) |
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

## Catching up on another agent's work
When asked "have we made progress on X in [#Space](space:sp…)" or what an agent concluded:
1. `hc ls` and filter terminals whose `where` starts with the space NAME (the `sp…` id in the link is not shown by `hc ls`; grepping `~/.config/herdr-app/data` for it only finds tab stores).
2. `hc read <t> | grep -n -i <topic or person>`, then read the surrounding history. The answer is what that agent actually said or did, plus its status (`done`/idle = nothing running since).
   Exactly what a Claude agent was sent and answered, older than the scrollback: its session transcript `~/.claude/projects/<cwd with / as ->/<session id>.jsonl` (session id is in Claude's status bar / `hc read`); scan `message.content` per line with python.
3. Report: built vs only analysed, the agent's open questions and unverified claims, then options 1/2/3 (draft a reply via CONTENT WRITER, verify via RESEARCH, wait).

## Project spaces: talk, hand work, split panes
- "The <project> agent" = the agent terminal in the Herdr space of that name: `hc ls`, match `where` prefix to the space name (case-insensitive), prefer `agent` = claude-code/codex/hermes. Talk with `hc send`, check with `hc read`. Several matches: ask which (options 1/2/3).
- New work for a running project agent: comment on its mirror card on the Hermes board (delivered with `hc send` once the agent is idle), or `hc send` directly if `hc ls` shows it idle. Chris is retiring Shepherdr, so don't create new `herdr-task` cards.
- Claude subtask in its own pane: start it as its own process (`hc run --bg --cwd <dir> claude`), then `herdr-app do terminal.keep --terminal <tX> --place right`. Claude's in-process subagents can't get a pane; they get a board card instead (below).
- Pane titles: set both. `herdr-app do pane.rename` serves plain-Herdr layouts (`chris-plain`). The terminal label `shepherdr.name` (`hc label <tX> "shepherdr.name=research: <title>"`) serves the Shepherdr `pane-chat` header (layout `chris`), which ignores `pane.rename`; drop the label once Shepherdr is uninstalled. Chris wants every agent pane titled with the agent plus what it's doing.
- Installed hooks: `herdr-panes` Hermes plugin (~/.hermes/plugins/herdr-panes/, `--selftest`): each kanban worker gets a pane beside The Muse tailing its log, titled `<assignee>: <card title>`, closed when the worker PID exits (`on_kanban_worker_exited` only fires on crash sweeps, never on clean completion). Map: ~/Tmp/the-muse/data/herdr-panes.json (stale entries pruned on next spawn). ~/.claude/herdr-subtask-hook.py (needs no Shepherdr): PreToolUse `Agent|Task` sets the label `muse.sub.<tool_use_id>=<description>` on its own terminal (`$HC_TERMINAL_ID`); SubagentStop and PostToolUse clear it. Use one label per subagent, because parallel subagents race on a shared value. Claude runs subagents async by default, so PostToolUse fires at launch: SubagentStop is the real "finished" event and must be in settings.json too. The plugin reads these labels from `hc ls`/`hc get --json` (remote terminals too) and keeps one card per subagent, idempotency key `herdr-subagent:<machine>/<terminal>/<tool_use_id>`, same `herdr-<space>` assignee. Don't kb-link it under the agent's card: a child of an open parent is gated to todo and can never show running. A remote machine needs only the hook file plus the three hook entries (PreToolUse/PostToolUse `Agent|Task`, SubagentStop) in its `~/.claude/settings.json`. Procedure per machine: read its HOME (`hc exec --on <m> -- sh -c 'echo $HOME'`), fetch the existing settings with `hc file read --on <m> <absolute path>`, MERGE the three entries in with Python (append to each event's list; assert every original key and hook entry is unchanged), save the result under `~/Tmp/the-muse/data/<m>-claude-settings.json`, then hand Chris the commands: `cp -p` backup on the remote, then `hc file write --on <m> <abs path> < <local file>` for the hook and the merged settings. Never overwrite a remote settings.json with a template: it can hold many other hooks and plugins. Afterwards verify the remote copy (`cmp` against the Mac hook, JSON loads, hook no-op rc 0, file mode unchanged). Labels set on a remote machine show up from the Mac. `hc exec` runs a non-login `sh` whose PATH lacks `~/.local/bin`, so `command -v claude` falsely says missing: test `$HOME/.local/bin/<bin>` directly.
- Any hook/plugin that calls Herdr (Chris's rule): first check Herdr is available (`shutil.which("hc")` + the binary it calls; `herdr-app` also needs ~/.config/herdr-app/herdr-app.sock) and return silently if not. Test the no-Herdr path by running with `PATH=/usr/bin:/bin`.
- Sending a project agent work and getting the answer: `hc send <t> "..."; hc wait <t> --timeout 90; hc read <t> | tail -25` (works for remote `machine/tN` too). Check `status` in `hc ls` first; `done`/idle = safe to send.
- Herdr task board internals (no view-only flag, how Start is refused, `list --all`, remote machines, status only for started tasks) and the one-board decision (Hermes kanban is Chris's single view; Herdr tasks and busy agents are mirrored onto it, comments relayed with `hc send`): `references/herdr-tasks.md`.
- One board = the Hermes kanban. herdr-panes' `on_kanban_dispatch_tick` (every 60s, in the gateway) mirrors every Herdr task (`herdr-task list --all`; skipped when `herdr-task` isn't installed) and every busy claude-code/codex terminal (`hc ls`, remote too) as a read-only card, assignee `herdr-<space>`. A non-profile assignee is never spawned. Herdr owns the state: todo→scheduled, working→running (claimed, heartbeat note), needs/Ready→blocked, done→done. A comment on a mirror card is `hc send` to its agent (waits while busy, never forces) and gets a "Delivered to tX" receipt. Agent cards (one per busy stretch, idempotency key `herdr-agent:*`) are archived a day after they finish so Done doesn't fill up; Herdr task cards follow Herdr's own archive. Self-test needs Hermes's python: `HERMES_HOME=$TMPDIR/st PYTHONPATH=~/.hermes/hermes-agent ~/.hermes/hermes-agent/venv/bin/python __init__.py --selftest` (plain python3 skips the board checks). Map: ~/Tmp/the-muse/data/herdr-sync.json. Plugin changes load only on `hermes gateway restart`, which Chris runs (blocked from inside the gateway). Hook changes in `~/.claude` are live at once for new Claude sessions. When a card finishes, compare the plugin file's mtime with the gateway start time again: workers often fix bugs after the restart, and those fixes need another one.
- `hc ls --json` has NO labels. To find terminals by label, use `hc get <t> --json` per terminal (or watch `hc events --json`). `herdr-app do pane.get` answers ok even for a pane that doesn't exist, so it proves nothing.
- Split beside a known pane: `herdr-app do pane.split --direction right --pane <pane id from herdr-app ls> --argv '["cmd",...]'`. Verified: the pane closes itself when argv exits; `herdr-app do pane.close --pane <id>` closes it early.

## Herdr app (desktop) layouts and mods
Adding, updating or placing mods, editing layouts, updating Shepherdr, or `shepherdr doctor` / a `held` machine sync: see `references/herdr-app-mods.md` (safe edit, third-party mod review/install, update checks against `herdr-setup` pins, Shepherdr local branch + sync-hold fixes).
