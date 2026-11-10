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
hermes/plugins/herdr-core-status   Hermes plugin: tells Herdr when Hermes works, waits on you, is idle
hermes/skills/herdr-terminals      Hermes skill: hc send/read/run, to talk to other agents
```

## New machine

1. Install Herdr, Bun, and (optionally) Hermes.
2. `bin/apply`: clones Shepherdr to `~/Projects/shepherdr` (or `$SHEPHERDR_DIR`), makes branch
   `local` from upstream main plus the patches, runs the checks, installs Shepherdr with your keys
   kept, applies the two post-install fixes, and installs the Hermes plugin and skill.
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
My own mods: edit in `~/.config/herdr-app/mods/<mod>`, copy `main.js`/`mod.json` back into `herdr/mods/<mod>`
and commit (`bin/apply` copies this repo's version over the installed one).

## What the patches do

| # | Change | Files | Why |
|---|---|---|---|
| 1 | Shepherdr's global keys moved into `layout:shepherdr`; terminal `ctrl-v` dropped | `keys.json` | Keys only apply while the Shepherdr layout is active. Breaks 2 keys tests on purpose |
| 2 | Files panel shows the `filetree` mod, labelled "Tree" | `layouts/shepherdr.json`, `mods/tabs-tasks/main.js` | Preferred tree view |
| 3 | Sidebar row shows a breathing dot while any agent in the space works | `mods/spaces-chat/main.js` | Upstream only shows spaces that need you |
| 3b | Sidebar row shows a green dot when work finished while you weren't looking, red when an agent reported an error you haven't looked at | `mods/spaces-chat/main.js` (`outcome`) | Same; green follows Herdr's "done", red the core status `error` |
| 3c | Right-click a pane's header: Rename pane. The name replaces the program's ("Claude Code"); empty restores it | `mods/pane-chat/main.js`, `mods/prompt-chat/main.js` (`setLabel` prop) | Stored as core label `shepherdr.name` on the terminal, so it survives Chat/Terminal swaps and shows on every screen |
| 4 | Hermes in the Chat view: history, tool rows, failed steps, questions answered from the card, Stop = Ctrl+C, the chat ends when Hermes exits | new `core/hermes.js` (copied into `mods/chat/core`, `mods/pane-chat/core` by `bin/sync-shared`, listed in `lib/COPIES`); hooks in `core/chat-log.js`, `core/chat-reader.js`, `mods/chat/main.js`, `mods/pane-chat/main.js`; `test/hermes.test.js` | Reads `~/.hermes/state.db`; the session comes from `~/.hermes/runtime/active_sessions.json` |
| 5 | Hermes plugin `herdr-core-status`: working / waiting on you / idle, and `error` when a turn fails (not when you stop it) | `hermes/plugins/` here | Hermes 0.23 runs turns in its gateway, so the plugin writes Herdr's status escape (OSC 7501, `msg` base64) to the CLI's tty |
| 6 | Hermes skill `herdr-terminals` | `hermes/skills/` here | Teaches Hermes `hc`, so its chat shows the messages it sends other agents |

Post-install fixes `bin/apply` makes every time: removes `ctrl-k` (jump) from `layout:shepherdr` in
`~/.config/herdr-app/keys.json` (only cmd-k wanted), and replaces `mods/tabs-tasks/main.js` with the
installer's `main.js.new` when it writes one.

Hermes limits: no approval cards, background jobs, slash or model menu; after `/new` the chat keeps
the first session until Hermes restarts; quitting Hermes mid-turn can leave the sidebar dot on;
depends on Hermes's state.db layout and its question picker's keys.
