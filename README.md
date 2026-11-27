# herdr-setup

My setup for the [Herdr](https://herdr.dev) app on top of plain Herdr: my own mods, a layout, other people's mods with my patches, keys, and the Hermes and Claude Code pieces that put every agent on one Hermes kanban. This repo holds only my changes. Herdr, Hermes and Claude Code are installed the usual way.

Not affiliated with Herdr, Hermes or Claude Code. MIT licensed, see LICENSE.

```
bin/apply                          set up a machine, or bring it up to date
herdr/mods/theeyes                 my mod: robot eyes whose mood follows every agent, errors and the Hermes crew (or ~/Tmp/the-muse/data/avatar.json)
herdr/mods/hc-pick                 my mod: ⌘⇧H lists terminals; Enter types an hc reference (address, space / tab, agent, session title) into the focused one
herdr/layouts/chris-plain.json     my layout: agent cards, the eyes and Sheepdog (added if missing, never overwritten)
herdr/third-party/mods.txt         other people's mods, pinned (Git Grapher, CI Dash, Agent Cards, T3 Actions); installed only when missing
herdr/third-party/*.patch          my changes to them (ci-dash.patch: other gh logins, plainer errors, "CI runs")
hermes/plugins/herdr-core-status   Hermes plugin: tells Herdr when Hermes works, waits on you, is idle, or a turn failed
hermes/plugins/herdr-panes         Hermes plugin: worker panes, Herdr agents on the Hermes kanban, comments to agents, crew counts for the eyes
hermes/skills/herdr-terminals      Hermes skill: hc send/read/run, to talk to other agents
hermes/command_allowlist.txt       what a Hermes Assistant runs without asking (bin/apply adds it to ~/.hermes/config.yaml)
claude/herdr-subtask-hook.py       Claude Code hook: one Hermes kanban card per subagent (settings-hooks.json wires it)
```

## New machine

1. Install Herdr, Bun, and (optionally) Hermes and Claude Code. `chris-plain` uses the Sheepdog and filetree mods, and `bin/apply` installs them. The Sheepdog mod also needs the `sheepdog` program from [kccarlos/herdr-sheepdog](https://github.com/kccarlos/herdr-sheepdog), which you install by hand.
2. Run `bin/apply`. It copies my mods and layout, installs the missing third-party mods with my patches, and adds the keys (⌘⌥G Git Grapher, ⌘⇧H hc-pick, and ⌘K / ⌘⇧K / ⌃⇧K for the picker in `chris-plain`). It only adds keys that are free. When Hermes is installed, it installs and enables both Hermes plugins and the skill, and adds the allowlist. When Claude Code is installed, it installs the subagent hook and adds its three entries to `~/.claude/settings.json`, after a backup.
3. In Herdr pick the `chris-plain` layout (Ctrl+Shift+L), and restart the Hermes gateway so `herdr-panes` loads.

Run `bin/apply` again after a change here or a new Herdr or Hermes release. It is safe to repeat: my mods get this repo's version, and everything else is only added when missing.

## Changing something

My own mods: edit in `~/.config/herdr-app/mods/<mod>`, run its `bun test`, copy `main.js`, `mod.json` and any other file it needs back into `herdr/mods/<mod>`, and commit. `bin/apply` copies this repo's version over the installed one. Hermes and Claude parts: edit them here, then run `bin/apply`. Other people's mods: to move one to a newer version, merge it into the installed copy, then set its commit in `herdr/third-party/mods.txt` and remake its patch (`diff -ru <upstream folder> <installed folder>`).

## Hermes kanban and Herdr

The Hermes kanban is the one board. The `herdr-panes` plugin runs inside the Hermes gateway and does four things. When a kanban worker starts, it opens a pane beside the Hermes terminal that shows the worker's log, names the pane after the card, and closes it when the worker exits. Once a minute it puts every busy Claude Code or Codex terminal on the board as a read-only card, on this machine and on every machine in `hc machine ls`, and it archives those cards a day after they finish. A comment on one of these cards goes to that agent with `hc send` when the agent is idle, and the card gets a receipt. Each Claude Code subagent also gets its own card. Run `python3 __init__.py --selftest` with Hermes's Python to check it. The plugin loads only when the Hermes gateway restarts.

The subagent cards come from `claude/herdr-subtask-hook.py`. Claude Code runs it on PreToolUse and PostToolUse for `Agent|Task` and on SubagentStop. It puts a `muse.sub.<id>` label on its own terminal while a subagent runs and removes the label when the subagent stops. The plugin reads these labels through `hc`, so a remote machine needs only the hook and `hc`. Outside Herdr the hook does nothing. `bin/apply` installs it on this machine and only adds the three entries to `~/.claude/settings.json`. For a remote machine, back up its settings, copy the hook with `hc file write --on <machine> <home>/.claude/herdr-subtask-hook.py`, and merge `claude/settings-hooks.json` into its `settings.json`. A Claude session that already runs picks up the hook only after it restarts.

Layout `chris-plain` uses Herdr's own mods plus Agent Cards, T3 Actions, the eyes, Sheepdog and the file tree. Git Grapher and CI Dash still open with their global keys. `bin/apply` adds its keys (⌘K, ⌘⇧K and ⌃⇧K open Herdr's picker). Pick it with Ctrl+Shift+L.
