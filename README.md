# herdr-setup

My changes to Shepherdr (a layout for the Herdr app) and the Hermes pieces that make Hermes a
Chat|Terminal agent in it. This repo holds only my changes. Shepherdr, Herdr and Hermes are installed
the usual way.

Built on [Shepherdr](https://github.com/eliasstravik/shepherdr) by Elias Stravik (MIT); not affiliated
with Shepherdr, Herdr or Hermes. MIT licensed, see LICENSE.

```
bin/apply                     set up a machine, or update to the latest Shepherdr (see below)
bin/export                    save the Shepherdr checkout's `local` branch back into shepherdr/patches
shepherdr/patches/*.patch     my commits on top of upstream Shepherdr (git format-patch)
shepherdr/BASE                the upstream commit/version they were last made on
herdr/mods/theeyes            my mod: robot eyes whose mood follows the focused tab's agent (or ~/Tmp/the-muse/data/avatar.json)
herdr/layouts/shepherdr-eyes.json  Shepherdr with the eyes under the sidebar (added if missing, never overwritten)
herdr/third-party/mods.txt    other people's mods, pinned (Git Grapher, CI Dash); installed only when missing
herdr/third-party/*.patch     my changes to them (ci-dash.patch: other gh logins, plainer errors, "CI runs")
hermes/plugins/herdr-core-status   Hermes plugin: tells Herdr when Hermes works, waits on you, is idle
hermes/skills/herdr-terminals      Hermes skill: hc send/read/run, to talk to other agents
hermes/command_allowlist.txt       what a Hermes Assistant runs without asking (bin/apply adds it to ~/.hermes/config.yaml)
```

## New machine

1. Install Herdr, Bun, and (optionally) Hermes.
2. `bin/apply`: clones Shepherdr to `~/Projects/shepherdr` (or `$SHEPHERDR_DIR`), makes branch
   `local` from upstream main plus the patches, runs the checks, installs Shepherdr with your keys
   kept, applies the two post-install fixes, installs the Hermes plugin and skill, and adds the
   Hermes Assistant's commands to Hermes's `command_allowlist`.
3. In Herdr pick the Shepherdr layout (Ctrl+Shift+L).

## Updating (new Shepherdr or Hermes release)

```sh
bin/apply          # fetch upstream, rebase `local` onto it, check, install
bin/export         # if the rebase changed anything (a conflict fixed), save it here
git commit -am "rebase on <version>"
```

A conflict stops `bin/apply` in the Shepherdr checkout. Fix the files (`git grep -n "local:"`
shows every line I touched in an upstream file; the table below says why), `git add`, `git rebase
--continue` (or `git am --continue` on a new machine), run `bin/apply` again, then `bin/export`.

## Changing something

Shepherdr part: edit and commit on branch `local` in the checkout (start the message with `local:`
and mark touched upstream lines with a `local:` comment), then `bin/export` and commit here.
Hermes part: edit under `hermes/` here, then `bin/apply --no-pull`.
Other people's mods: to move one to a newer version, merge it into the installed copy, then set its
commit in `herdr/third-party/mods.txt` and remake its patch (`diff -ru <upstream folder> <installed folder>`).
My own mods: edit in `~/.config/herdr-app/mods/<mod>`, copy `main.js`/`mod.json` back into `herdr/mods/<mod>`
and commit (`bin/apply` copies this repo's version over the installed one).

## What the patches do

| # | Change | Files | Why |
|---|---|---|---|
| 1 | Shepherdr's global keys moved into `layout:shepherdr`; terminal `ctrl-v` dropped | `keys.json` | Keys only apply while the Shepherdr layout is active. Breaks 2 keys tests on purpose |
| 2 | Files panel shows the `filetree` mod, labelled "Tree" | `layouts/shepherdr.json`, `mods/tabs-tasks/main.js` | Preferred tree view |
| 3 | Sidebar row shows a breathing dot while any agent in the space works | `mods/spaces-chat/main.js` | Upstream only shows spaces that need you |
| 3b | Sidebar row shows a green dot when work finished while you weren't looking, red when an agent reported an error you haven't looked at | `mods/spaces-chat/main.js` (`outcome`) | Same; green follows Herdr's "done", red the core status `error` |
| 3c | Right-click a pane's header: a menu like a tab's with Rename…. The name replaces the program's ("Claude Code"); empty restores it | `mods/pane-chat/main.js`, `mods/menu-tasks/main.js` (`pane-head` menu), `mods/prompt-chat/main.js` (`setLabel` prop) | Stored as core label `shepherdr.name` on the terminal, so it survives Chat/Terminal swaps and shows on every screen |
| 4 | Hermes in the Chat view: history, tool rows, failed steps, questions answered from the card, Stop = Ctrl+C, the chat ends when Hermes exits | new `core/hermes.js` (copied into `mods/chat/core`, `mods/pane-chat/core` by `bin/sync-shared`, listed in `lib/COPIES`); hooks in `core/chat-log.js`, `core/chat-reader.js`, `mods/chat/main.js`, `mods/pane-chat/main.js`; `test/hermes.test.js` | Reads `~/.hermes/state.db`; the session comes from `~/.hermes/runtime/active_sessions.json` |
| 5 | Hermes plugin `herdr-core-status`: working / waiting on you / idle, and `error` when a turn fails (not when you stop it) | `hermes/plugins/` here | Hermes 0.23 runs turns in its gateway, so the plugin writes Herdr's status escape (OSC 7501, `msg` base64) to the CLI's tty |
| 6 | Hermes skill `herdr-terminals` | `hermes/skills/` here | Teaches Hermes `hc`, so its chat shows the messages it sends other agents |
| 7 | Hermes as the **Assistant**: Settings (Assistant row only), the New space dialog and the chat's model menu offer Hermes when it is installed. Model: Hermes's own default or one typed by id (`-m`). Permissions: Auto (plain `hermes`) or Full access (`--yolo`) | `core/hermes.js` (`hermesMenu`, `hermesArgv`, `hermesCurrent`, `withoutHermes`; now also copied into `chat-models`, `newspace`, `shepherdr-settings`, `coordinator`); hooks in `core/agents.js`, `lib/settings.js`, `mods/shepherdr-settings/main.js`, `mods/chat/main.js`, `mods/chat-models/main.js`, `herdr_task/settings.py` (`argv_for`); `test/hermes.test.js`, `test/test_hermes_settings.py` | Workers and the Reviewer keep Claude Code and Codex: `herdr-task`'s first prompt and resume don't know Hermes |
| 8 | A restart from a Hermes agent (to another agent, or another Hermes) hands over its last 40 messages in a file beside the saved screen, and a `sqlite3` line to read more | new `mods/coordinator/hermes-history.sh`; hook in `mods/coordinator/restart.sh` | Hermes has no log file per session; found as `HERMES_FIND` does (`active_sessions.json` + `state.db`) |
| 9 | Auto approvals: `bin/apply` adds `hermes/command_allowlist.txt` (`herdr-task`, `hc`, `herdr-artifact`, `herdr-secret`, read-only `git`) to `command_allowlist` in `~/.hermes/config.yaml` through Hermes's own config code; it only adds | `bin/apply`, `hermes/` here | The chat has no approval cards for Hermes, and Hermes has no per-launch allowlist flag |
| 10 | The picker under a running Assistant's chat offers Hermes (patch 18) | `mods/chat/main.js` (`openPicker`) | It built only Claude Code and Codex menus. (The tab's Switch agent needing `setsid`, and restart.sh's `mapfile` under macOS's bash 3.2, were fixed here first; upstream fixed both in 3.1.33, #736, so those parts are dropped) |
| 11 | A coordinator script (restart, close, a task's switch) that fails in the background shows a toast; `restart.sh` says when Herdr started no agent (patch 19) | new `mods/coordinator/run-or-toast.sh`, started through upstream's `DETACH` by `lib/coordinator.js` (`script`, copied into each mod); `mods/toasts/main.js` (reads `data/coordinator/failed.txt` every 3 s); `mods/coordinator/restart.sh` | The scripts run detached with their output thrown away, so a failure vanished; upstream has no toast for it |
| 12 | A tab's Switch agent keeps an agent that lives behind a chat behind it (patch 20): its `herdr.chat`, else its Assistant slot's pane, else the one chat pane in its Assistant tab. A new Hermes gets its first message (template + handoff) once ready, plus its own terminal id. The Hermes plugin reports idle when a CLI opens its session | `lib/coordinator.js` (`chatOf`, `restartAgent`, `script`'s env); `mods/coordinator/restart.sh`; `hermes/plugins/herdr-core-status` (`on_session_open`) here | An Assistant that lost its `herdr.chat` label restarted as a new pane in the tab, outside its chat. A new Hermes reported no status until its first turn, so hc never sent the first message: restart.sh waited out 90 s first. Hermes's tool shell has no `HC_TERMINAL_ID` |

Post-install fixes `bin/apply` makes every time: removes `ctrl-k` (jump) from `layout:shepherdr` in
`~/.config/herdr-app/keys.json` (only cmd-k wanted), and replaces `mods/tabs-tasks/main.js` with the
installer's `main.js.new` when it writes one.

Hermes limits: no approval cards (Auto still stops at a risky command outside the allowlist, like a hard git reset:
answer it in the terminal, or pick Full access), background jobs or slash menu; not for task workers or the Reviewer;
no reasoning level; the web app's Settings don't offer it (only the window's); a model change restarts it with a
handoff, never in the same session; the allowlist matches a whole command, so one with a pipe, `;` or `&&` can still
ask; after `/new` the chat keeps
the first session until Hermes restarts; quitting Hermes mid-turn can leave the sidebar dot on;
depends on Hermes's state.db layout and its question picker's keys.
