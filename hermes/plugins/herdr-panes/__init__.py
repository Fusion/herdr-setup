"""herdr-panes: one Herdr pane per kanban worker, beside The Muse's Hermes pane.

on_kanban_worker_spawned -> split The Muse's pane to the right, tail the worker log, name it.
on_kanban_worker_exited  -> close that pane.
task_id -> pane map lives in ~/Tmp/the-muse/data/herdr-panes.json.

on_kanban_worker_exited only fires when the dispatcher's crash sweep reaps a worker, not on a
clean finish. So the pane's own command also watches the worker PID and exits with it, and a
Herdr pane closes when its program exits.

Every failure logs a warning and returns: nothing here may raise into the dispatcher.
Run `python3 __init__.py --selftest` to check the map logic.
"""

from __future__ import annotations

import json
import logging
import os
import shlex
import shutil
import sqlite3
import subprocess
from pathlib import Path

log = logging.getLogger("herdr-panes")

MAP_PATH = Path.home() / "Tmp/the-muse/data/herdr-panes.json"
LOG_DIR = Path.home() / ".hermes/kanban/logs"
KANBAN_DB = Path.home() / ".hermes/kanban.db"
SPACE = "Work In Progress"
AGENT = "hermes"
SOCK = Path.home() / ".config/herdr-app/herdr-app.sock"


def herdr_available() -> bool:
    """hc + herdr-app installed and the app's socket present; else every hook is a silent no-op."""
    return bool(shutil.which("hc") and shutil.which("herdr-app") and SOCK.exists())


# ---- map (pure, covered by --selftest) -------------------------------------------------------

def load_map(path: Path | None = None) -> dict:
    try:
        path = path or MAP_PATH
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def save_map(m: dict, path: Path | None = None) -> None:
    path = path or MAP_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(m, indent=1, sort_keys=True))
    os.replace(tmp, path)


def put(m: dict, task_id: str, pane: str, pid) -> dict:
    m[task_id] = {"pane": pane, "pid": pid}
    return m


def pop(m: dict, task_id: str):
    """Remove and return the pane id for task_id, or None."""
    return (m.pop(task_id, None) or {}).get("pane")


def prune(m: dict, alive) -> dict:
    """Drop entries whose worker is gone (their pane closed itself)."""
    return {k: v for k, v in m.items() if v.get("pid") and alive(v["pid"])}


def muse_pane(ls: dict):
    """Pane id of the hermes terminal in SPACE, or None."""
    for sp in ls.get("spaces", []):
        if sp.get("name") != SPACE:
            continue
        for tab in sp.get("tabs", []):
            for t in tab.get("terminals", []):
                if t.get("app") == AGENT:
                    return t.get("pane")
    return None


# ---- herdr + hooks ---------------------------------------------------------------------------

def _alive(pid) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError, TypeError):
        return False


def _herdr(*args) -> dict:
    r = subprocess.run(["herdr-app", *args], capture_output=True, text=True, timeout=5,
                       stdin=subprocess.DEVNULL)
    if r.returncode != 0:
        raise RuntimeError(f"herdr-app {args[:2]} rc={r.returncode}: {r.stderr.strip()[:200]}")
    return json.loads(r.stdout) if r.stdout.strip() else {}


def _title(task_id: str) -> str:
    try:
        with sqlite3.connect(f"file:{KANBAN_DB}?mode=ro", uri=True, timeout=2) as c:
            row = c.execute("SELECT title FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return row[0] if row else task_id
    except sqlite3.Error:
        return task_id


def _pane_cmd(task_id: str, pid) -> list:
    logf = shlex.quote(str(LOG_DIR / f"{task_id}.log"))
    if not pid:
        return ["tail", "-f", str(LOG_DIR / f"{task_id}.log")]
    # tail until the worker exits, then end so Herdr closes the pane (macOS tail has no --pid).
    return ["/bin/sh", "-c",
            f"tail -n +1 -F {logf} & t=$!; while kill -0 {int(pid)} 2>/dev/null; do sleep 2; done; kill $t"]


def on_spawned(task_id: str = "", assignee=None, worker_pid=None, **_):
    if not herdr_available():
        return
    try:
        pane = muse_pane(_herdr("ls"))
        if not pane:
            log.warning("herdr-panes: no %s pane in space %r; skipping %s", AGENT, SPACE, task_id)
            return
        out = _herdr("do", "pane.split", "--direction", "right", "--pane", pane,
                     "--argv", json.dumps(_pane_cmd(task_id, worker_pid)))
        new, label = out["pane"], f"{assignee}: {_title(task_id)}"
        _herdr("do", "pane.rename", "--pane", new, "--name", label)
        # Chris's pane-chat header shows the terminal's shepherdr.name label, not the pane name.
        # ponytail: Shepherdr exit step 4 drops this label; pane.rename above is the lasting title.
        subprocess.run(["hc", "label", out["terminal"], f"shepherdr.name={label}"],
                       capture_output=True, timeout=5, stdin=subprocess.DEVNULL)
        save_map(put(prune(load_map(), _alive), task_id, new, worker_pid))
    except Exception as exc:
        log.warning("herdr-panes: spawn %s: %s", task_id, exc)


def on_exited(task_id: str = "", **_):
    if not herdr_available():
        return
    try:
        m = load_map()
        pane = pop(m, task_id)
        save_map(m)
        if pane:
            _herdr("do", "pane.close", "--pane", pane)
    except Exception as exc:  # pane already gone when the worker's own exit closed it
        log.warning("herdr-panes: exit %s: %s", task_id, exc)


# ---- mirror: Herdr tasks + busy Herdr agents as read-only cards on the Hermes board ------------
#
# Map (SYNC_PATH):
#   {"tasks":  {"<herdr task key>": {"card": "t_..", "folder": "/path", "note": "<last note>"}},
#    "agents": {"<hc address>":     {"card": "t_..", "note": "<last note>"}}}
# Part A entries stay until the Herdr task is gone (then the card is archived).
# Part B entries are dropped when the stretch ends (card completed); the next stretch gets a new card.
# Card bodies carry the Herdr key / terminal address too, as `Herdr task: <key>` / `Terminal: <address>`.
# Read-only towards Herdr: only `herdr-task list` and `hc ls` / `hc get`.

SYNC_PATH = Path.home() / "Tmp/the-muse/data/herdr-sync.json"
AGENTS = {"claude-code", "codex"}
CLAIM_TTL = 600  # renewed every 60s tick; a dead gateway lets the dispatcher reclaim after 10 min
MIRROR_TAG = "Mirror card: Herdr owns it, Hermes never runs it."


def slug(name: str) -> str:
    out = "".join(c if c.isalnum() else "-" for c in (name or "").lower())
    return "-".join(p for p in out.split("-") if p) or "unknown"


def task_want(v: dict | None) -> tuple:
    """Herdr task view (herdr-task list --json) or None -> (Hermes status, note). Pure.

    To do / queued / scheduled -> 'scheduled', not 'ready': a ready card with a non-profile assignee
    raises stranded_in_ready after 30 min (kanban_diagnostics._rule_stranded_in_ready); scheduled is
    never dispatched and has no diagnostic. Ready (waits for Accept) -> 'blocked', never 'review'.
    """
    if v is None:
        return "archived", "Removed or archived in Herdr"
    st, text = v.get("status"), v.get("status_text") or v.get("status") or "?"
    if st in ("todo", "queued", "scheduled"):
        why = v.get("why") or v.get("reason")
        return "scheduled", f"{text} in Herdr" + (f": {why}" if why else "")
    if st in ("working", "merging"):
        rep = (v.get("report") or {}).get("text")
        return "running", text + (f": {rep}" if rep else "")
    if st == "needs":
        return "blocked", v.get("why") or "Needs you in Herdr"
    if st == "ready":
        return "blocked", "Ready for your Accept in Herdr"
    if st == "done":
        return "done", "Done in Herdr"
    return "scheduled", f"{text} in Herdr"


def agent_want(status, title: str = "") -> tuple:
    """hc terminal status ('working' | 'blocked' | 'done' | 'idle' | None) -> (Hermes status, note). Pure."""
    if status == "working":
        return "running", title or "working"
    if status == "blocked":
        return "blocked", "waiting for you in Herdr"
    return "done", f"Agent {status or 'gone'} in Herdr"


def _run_json(*argv):
    r = subprocess.run(list(argv), capture_output=True, text=True, timeout=20, stdin=subprocess.DEVNULL)
    if r.returncode != 0:
        raise RuntimeError(f"{argv[:2]} rc={r.returncode}: {r.stderr.strip()[:200]}")
    return json.loads(r.stdout)


def _reconcile(kb, kbd, conn, tid: str, want: str, note: str, note_changed: bool) -> str:
    """Move card tid toward `want`; returns its status afterwards ('gone' if missing/archived)."""
    t = kb.get_task(conn, tid)
    cur = t.status if t else "archived"
    if cur == "archived":
        return "gone"
    if want == "archived":
        kb.archive_task(conn, tid)
        return "gone"
    if cur == "done":
        return "done"  # ponytail: a Herdr reopen of a done task is not mirrored back
    if cur == want and not (want == "blocked" and note_changed):
        if cur == "running":
            kb.heartbeat_claim(conn, tid, ttl_seconds=CLAIM_TTL, claimer=_claimer(kb))
            if note_changed:
                kbd.heartbeat_worker(conn, tid, note=note)
        return cur
    if cur in ("scheduled", "blocked"):
        kb.unblock_task(conn, tid)  # back to ready: the one state every transition below accepts
    if want == "done":
        kb.complete_task(conn, tid, result=note, summary=note, force=True)
    elif want == "scheduled":
        kb.schedule_task(conn, tid, reason=note)
    elif want == "blocked":
        # Same-kind re-block counts toward BLOCK_RECURRENCE_LIMIT (2) and lands in triage; a mirror
        # card blocks every time Herdr waits on Chris, so the sync clears that counter on its own cards.
        with kb.write_txn(conn):
            conn.execute("UPDATE tasks SET block_recurrences = 0 WHERE id = ?", (tid,))
        kb.block_task(conn, tid, reason=note, kind="needs_input")
    elif want == "running":
        if kb.claim_task(conn, tid, ttl_seconds=CLAIM_TTL, claimer=_claimer(kb)):
            kbd.heartbeat_worker(conn, tid, note=note)
    t = kb.get_task(conn, tid)
    return t.status if t else "gone"


def _claimer(kb) -> str:
    return kb._host_prefix() + "herdr-mirror"


def _new_card(kb, conn, title, assignee, body, key):
    tid = kb.create_task(conn, title=title, body=body, assignee=assignee, created_by="herdr-mirror",
                         idempotency_key=key)
    log.info("herdr-mirror: card %s for %s", tid, key)
    return tid


def _sync_tasks(kb, kbd, conn, m, spaces):
    if shutil.which("herdr-task") is None:
        return  # Shepherdr gone; this whole Part A mirror is deleted in Shepherdr exit step 4
    groups = _run_json("herdr-task", "list", "--all", "--json")
    seen = {}
    for g in groups:
        for v in g.get("tasks", []):
            seen[v["key"]] = (g, v)
    tasks = m.setdefault("tasks", {})
    for key, (g, v) in seen.items():
        want, note = task_want(v)
        e = tasks.get(key)
        if e is None:
            if want == "done":
                continue  # finished before we ever saw it: no card
            space = spaces.get(v.get("space")) or g.get("name") or ""
            body = (f"Herdr task: {key}\nRef: {v.get('ref')}\nFolder: {v.get('folder')}\nSpace: {space}\n\n"
                    f"{MIRROR_TAG}")
            e = tasks[key] = {"card": _new_card(kb, conn, f"{v.get('ref')}: {v.get('title')}",
                                                f"herdr-{slug(space)}", body, f"herdr-task:{key}"),
                              "folder": v.get("folder"), "note": None}
        _reconcile(kb, kbd, conn, e["card"], want, note, note != e.get("note"))
        e["note"] = note
    for key in [k for k in tasks if k not in seen]:
        e = tasks[key]
        if e.get("folder") and not os.path.isdir(e["folder"]):
            continue  # folder offline (unmounted volume): its tasks are not gone
        want, note = task_want(None)
        _reconcile(kb, kbd, conn, e["card"], want, note, True)
        del tasks[key]


def _sync_agents(kb, kbd, conn, m):
    ls = _run_json("hc", "ls", "--json")
    down = {x["name"] for x in ls.get("machines", []) if x.get("state") != "connected"}
    terms = {t["address"]: t for t in ls.get("terminals", [])}
    agents = m.setdefault("agents", {})
    for addr, t in terms.items():
        if t.get("agent") not in AGENTS or addr in agents or t.get("status") != "working":
            continue
        d = _run_json("hc", "get", addr, "--json")
        if "herdr.task" in (d.get("labels") or {}):
            continue
        where = t.get("where") or addr
        body = f"Terminal: {addr}\nAgent: {t['agent']}\nWhere: {where}\nCwd: {t.get('cwd')}\n\n{MIRROR_TAG}"
        agents[addr] = {"card": _new_card(kb, conn, f"{t['agent']} in {where}",
                                          f"herdr-{slug(where.split(' / ')[0])}", body,
                                          f"herdr-agent:{addr}:{t.get('turn')}"), "note": None}
    for addr in list(agents):
        e, t = agents[addr], terms.get(addr)
        if t is None and addr.split("/")[0] in down:
            continue  # machine unreachable: keep the card as it is
        title = ""
        if t and t.get("status") == "working":
            title = _run_json("hc", "get", addr, "--json").get("title") or ""
        want, note = agent_want(t and t.get("status"), title)
        if _reconcile(kb, kbd, conn, e["card"], want, note, note != e.get("note")) in ("done", "gone"):
            del agents[addr]
        else:
            e["note"] = note


SUB_PREFIX = "muse.sub."  # set by ~/.claude/herdr-subtask-hook.py: muse.sub.<tool_use_id>=<description>


def _sub_key(addr: str, tool_use_id: str) -> str:
    """Map + idempotency key: <machine>/<terminal>/<tool_use_id>, 'local' for this Mac. Pure."""
    return f"{addr if '/' in addr else 'local/' + addr}/{tool_use_id}"


def _live_subagents():
    """Subagents listed on busy agent terminals, every machine: ({key: (title, where)}, down machines)."""
    ls = _run_json("hc", "ls", "--json")
    down = {x["name"] for x in ls.get("machines", []) if x.get("state") != "connected"}
    live = {}
    for t in ls.get("terminals", []):
        # every agent terminal, idle too: an async subagent (Claude's default) runs while its parent is idle.
        # ponytail: a subagent that dies without SubagentStop keeps its card running until the terminal ends.
        if t.get("agent") not in AGENTS:
            continue
        for k, v in (_run_json("hc", "get", t["address"], "--json").get("labels") or {}).items():
            if k.startswith(SUB_PREFIX):
                live[_sub_key(t["address"], k[len(SUB_PREFIX):])] = (f"{t['agent']}: {v}", t.get("where") or t["address"])
    return live, down


def _sync_subagents(kb, kbd, conn, m, live, down):
    """One card per Claude subagent: running while its label is listed, done once it leaves.
    Not linked under the agent's card: a child of an open parent is gated to todo and can't run."""
    subs = m.setdefault("subagents", {})
    for key, (title, where) in live.items():
        if key not in subs:
            body = f"Subagent: {key}\nWhere: {where}\n\n{MIRROR_TAG}"
            subs[key] = {"card": _new_card(kb, conn, title, f"herdr-{slug(where.split(' / ')[0])}", body,
                                           f"herdr-subagent:{key}")}
        _reconcile(kb, kbd, conn, subs[key]["card"], "running", title, False)
    for key in [k for k in subs if k not in live]:
        if key.split("/")[0] in down:
            continue  # machine unreachable: keep the card as it is
        _reconcile(kb, kbd, conn, subs[key]["card"], "done", "Subagent finished", True)
        del subs[key]


ARCHIVE_AFTER = 86400  # finished agent cards (one per busy stretch) leave Done after a day


def _archive_old(kb, conn, now=None):
    """Archive Part B agent cards that finished more than ARCHIVE_AFTER ago. Herdr task cards are left
    alone: Herdr archives its own done tasks after a week and the sync archives the card then."""
    import time
    cutoff = (now or time.time()) - ARCHIVE_AFTER
    rows = conn.execute("SELECT id FROM tasks WHERE created_by = ? AND status = 'done' "
                        "AND (idempotency_key LIKE 'herdr-agent:%' OR idempotency_key LIKE 'herdr-subagent:%') "
                        "AND completed_at < ?",
                        (MIRROR_AUTHOR, int(cutoff))).fetchall()
    for (tid,) in rows:
        kb.archive_task(conn, tid)
    return [r[0] for r in rows]


# ---- comments: Chris's card comments -> the Herdr agent behind the card -------------------------
#
# Each map entry keeps "cursor" = id of the last comment handled. The only write to Herdr in this
# plugin is `hc send <address> <comment text>`. A busy agent makes hc send refuse: the comment stays
# pending and is retried next tick. Never --force.

MIRROR_AUTHOR = "herdr-mirror"
RECEIPTS = ("Delivered to ", "Not delivered: ")


def pending(comments, cursor) -> list:
    """Comments after cursor that a person wrote (not the sync, not a receipt). Pure."""
    return [c for c in comments if c.id > (cursor or 0) and c.author != MIRROR_AUTHOR
            and not c.body.startswith(RECEIPTS)]


def _task_agent(key: str, folder) -> str | None:
    argv = ["herdr-task", "show", key, "--json"] + (["--folder", folder] if folder else [])
    live = _run_json(*argv).get("live") or []
    return next((x.get("address") for x in live if x.get("address")), None)


def _deliver(kb, conn, m, send=None, now=None):
    """Send pending comments of every open mirror card; one comment per card per tick, in order."""
    import time
    send = send or (lambda a, text: subprocess.run(["hc", "send", a, text], capture_output=True, text=True,
                                                   timeout=20, stdin=subprocess.DEVNULL).returncode == 0)
    now = now or (lambda: time.strftime("%Y-%m-%d %H:%M:%S %Z"))
    entries = [(e, lambda k=k, e=e: _task_agent(k, e.get("folder"))) for k, e in m.get("tasks", {}).items()]
    entries += [(e, lambda a=a: a) for a, e in m.get("agents", {}).items()]
    for e, target in entries:
        try:
            t = kb.get_task(conn, e["card"])
            if not t or t.status in ("done", "archived"):
                continue
            todo = pending(kb.list_comments(conn, e["card"]), e.get("cursor"))
            if not todo:
                continue
            c, addr = todo[0], target()
            if not addr:
                kb.add_comment(conn, e["card"], MIRROR_AUTHOR, "Not delivered: no agent is running this Herdr task")
            elif send(addr, c.body):
                kb.add_comment(conn, e["card"], MIRROR_AUTHOR, f"Delivered to {addr} at {now()}")
            else:
                continue  # busy: retry next tick
            e["cursor"] = c.id
        except Exception as exc:
            log.warning("herdr-mirror: deliver %s: %s", e.get("card"), exc)


# ---- crew: running / blocked Hermes cards for the theeyes mod (~/Tmp/the-muse/data/crew.json) -------

CREW_PATH = Path.home() / "Tmp/the-muse/data/crew.json"


def crew_counts(conn) -> dict:
    """Running / blocked cards of real profiles: not the mirror's herdr-* cards, not its authorship."""
    rows = conn.execute("SELECT status, COUNT(*) FROM tasks WHERE status IN ('running', 'blocked') "
                        "AND assignee IS NOT NULL AND assignee NOT LIKE 'herdr-%' "
                        "AND COALESCE(created_by, '') != ? GROUP BY status", (MIRROR_AUTHOR,)).fetchall()
    return {"running": 0, "blocked": 0, **dict(rows)}


def write_crew(conn, path: Path | None = None, now=None) -> dict:
    import time
    c = {**crew_counts(conn), "ts": int(now if now is not None else time.time())}
    save_map(c, path or CREW_PATH)  # tmp + os.replace: atomic
    return c


def on_tick(board=None, dry_run=False, outcome=None, **_):
    if not herdr_available():
        return
    if dry_run or outcome == "skipped_locked" or board not in (None, "default"):
        return  # skipped_locked: another dispatcher owns this tick, let it sync
    try:
        from hermes_cli import kanban_db as kb, kanban_db_dispatch as kbd
        from hermes_cli.kanban_db_connect import connect
        m = load_map(SYNC_PATH)
        try:
            spaces = {s["id"]: s["name"] for s in _herdr("ls").get("spaces", [])}
        except Exception:
            spaces = {}
        conn = connect()
        try:
            # deliver first: a Part B card is completed by the sync the tick its agent goes idle,
            # and that idle moment is exactly when a pending comment can be delivered.
            for part in (lambda: _deliver(kb, conn, m), lambda: _sync_tasks(kb, kbd, conn, m, spaces),
                         lambda: _sync_agents(kb, kbd, conn, m),
                         lambda: _sync_subagents(kb, kbd, conn, m, *_live_subagents()),
                         lambda: _archive_old(kb, conn), lambda: write_crew(conn)):
                try:
                    part()
                except Exception as exc:
                    log.warning("herdr-mirror: %s", exc)
        finally:
            conn.close()
            save_map(m, SYNC_PATH)
    except Exception as exc:
        log.warning("herdr-mirror: tick: %s", exc)


def register(ctx):
    ctx.register_hook("on_kanban_worker_spawned", on_spawned)
    ctx.register_hook("on_kanban_worker_exited", on_exited)
    ctx.register_hook("on_kanban_dispatch_tick", on_tick)


def _selftest():
    import tempfile
    p = Path(tempfile.mkdtemp()) / "m.json"
    assert load_map(p) == {}
    m = put(put({}, "t_a", "p1", 101), "t_b", "p2", 102)
    save_map(m, p)
    assert load_map(p) == {"t_a": {"pane": "p1", "pid": 101}, "t_b": {"pane": "p2", "pid": 102}}
    assert pop(m, "t_a") == "p1" and pop(m, "t_a") is None and list(m) == ["t_b"]
    assert prune({"x": {"pane": "p", "pid": 1}, "y": {"pane": "q", "pid": 2}}, lambda pid: pid == 2) == {"y": {"pane": "q", "pid": 2}}
    ls = {"spaces": [{"name": "Other", "tabs": [{"terminals": [{"app": "hermes", "pane": "nope"}]}]},
                     {"name": SPACE, "tabs": [{"terminals": [{"app": "claude-code", "pane": "c"},
                                                             {"app": "hermes", "pane": "muse"}]}]}]}
    assert muse_pane(ls) == "muse" and muse_pane({}) is None
    # mirror state mapping
    assert slug("Work In Progress") == "work-in-progress" and slug("amd-ml / 2") == "amd-ml-2" and slug("") == "unknown"
    assert task_want(None)[0] == "archived"
    for st in ("todo", "queued", "scheduled"):
        assert task_want({"status": st, "status_text": "X"})[0] == "scheduled"
    assert task_want({"status": "queued", "status_text": "Queued", "reason": "after HMS-1"}) == ("scheduled", "Queued in Herdr: after HMS-1")
    assert task_want({"status": "working", "status_text": "Working", "report": {"text": "tests"}}) == ("running", "Working: tests")
    assert task_want({"status": "merging", "status_text": "Merging"}) == ("running", "Merging")
    assert task_want({"status": "needs", "why": "Asks: which DB?"}) == ("blocked", "Asks: which DB?")
    assert task_want({"status": "needs"}) == ("blocked", "Needs you in Herdr")
    assert task_want({"status": "ready"}) == ("blocked", "Ready for your Accept in Herdr")
    assert task_want({"status": "done"})[0] == "done"
    assert agent_want("working", "Fix login") == ("running", "Fix login")
    assert agent_want("blocked") == ("blocked", "waiting for you in Herdr")
    assert agent_want("done")[0] == agent_want("idle")[0] == agent_want(None)[0] == "done"
    _selftest_reconcile()
    print("selftest ok")


def _selftest_reconcile():
    """Drive one card through every mirror transition on a throwaway board (needs hermes_cli)."""
    import tempfile
    try:
        from hermes_cli import kanban_db as kb, kanban_db_dispatch as kbd
        from hermes_cli.kanban_db_connect import connect
    except ImportError:
        print("reconcile: skipped (run with the hermes python to cover it)")
        return
    conn = connect(Path(tempfile.mkdtemp()) / "kanban.db")
    tid = _new_card(kb, conn, "HMS-1: t", "herdr-x", "b", "herdr-task:k")
    path = []
    for want, note in [("scheduled", "To do"), ("running", "Working"), ("running", "Working: step 2"),
                       ("blocked", "Asks"), ("running", "Working"), ("blocked", "Asks"), ("running", "W"),
                       ("blocked", "Asks again"), ("blocked", "Ready for your Accept in Herdr"),
                       ("scheduled", "Queued"), ("done", "Done in Herdr"), ("running", "late")]:
        path.append(_reconcile(kb, kbd, conn, tid, want, note, True))
    assert path == ["scheduled", "running", "running", "blocked", "running", "blocked", "running",
                    "blocked", "blocked", "scheduled", "done", "done"], path
    t = kb.get_task(conn, tid)
    assert t.block_recurrences == 0 and not t.claim_lock, (t.block_recurrences, t.claim_lock)
    notes = [json.loads(r[0] or "{}").get("note") for r in conn.execute(
        "SELECT payload FROM task_events WHERE task_id=? AND kind='heartbeat'", (tid,))]
    assert "Working: step 2" in notes, notes
    assert conn.execute("SELECT COUNT(*) FROM kanban_notify_subs WHERE task_id=?", (tid,)).fetchone()[0] == 0
    assert _reconcile(kb, kbd, conn, tid, "archived", "gone", True) == "gone"
    assert kb.get_task(conn, tid).status == "archived"
    print("reconcile: ok", path)
    _selftest_deliver(kb, conn)
    # archive: an agent card done > a day ago goes; a fresh one and a Herdr task card stay
    import time
    old, fresh = (_new_card(kb, conn, "claude-code in x", "herdr-x", "b", f"herdr-agent:{k}") for k in ("o:1", "f:1"))
    task = _new_card(kb, conn, "HMS-9: t", "herdr-x", "b", "herdr-task:k9")
    for t in (old, fresh, task):
        kb.complete_task(conn, t, result="r", summary="r", force=True)
    with kb.write_txn(conn):
        conn.execute("UPDATE tasks SET completed_at = ? WHERE id IN (?, ?)", (int(time.time()) - 2 * ARCHIVE_AFTER, old, task))
    assert _archive_old(kb, conn) == [old], "archive picked the wrong cards"
    assert [kb.get_task(conn, t).status for t in (old, fresh, task)] == ["archived", "done", "done"]
    print("archive: ok")
    # subagent cards: add -> running, unreachable machine keeps it, gone -> done, old done -> archived
    assert _sub_key("t5", "toolu_a") == "local/t5/toolu_a" and _sub_key("vast/t2", "x") == "vast/t2/x"
    m = {}
    live = {"local/t5/toolu_a": ("claude-code: sleep", "Work In Progress / 1"),
            "vast/t2/toolu_b": ("claude-code: train", "amd-ml / 2")}
    _sync_subagents(kb, kbd, conn, m, live, set())
    _sync_subagents(kb, kbd, conn, m, live, set())  # idempotent: no second card
    a, b = m["subagents"]["local/t5/toolu_a"]["card"], m["subagents"]["vast/t2/toolu_b"]["card"]
    ta = kb.get_task(conn, a)
    assert (ta.status, ta.title, ta.assignee, ta.created_by) == ("running", "claude-code: sleep",
                                                                "herdr-work-in-progress", MIRROR_AUTHOR), ta
    assert kb.get_task(conn, b).assignee == "herdr-amd-ml"
    assert conn.execute("SELECT COUNT(*) FROM tasks WHERE idempotency_key LIKE 'herdr-subagent:%'").fetchone()[0] == 2
    _sync_subagents(kb, kbd, conn, m, {}, {"vast"})
    assert [kb.get_task(conn, t).status for t in (a, b)] == ["done", "running"] and list(m["subagents"]) == ["vast/t2/toolu_b"]
    _sync_subagents(kb, kbd, conn, m, {}, set())
    assert kb.get_task(conn, b).status == "done" and m["subagents"] == {}
    assert conn.execute("SELECT COUNT(*) FROM kanban_notify_subs WHERE task_id IN (?, ?)", (a, b)).fetchone()[0] == 0
    with kb.write_txn(conn):
        conn.execute("UPDATE tasks SET completed_at = ? WHERE id = ?", (int(time.time()) - 2 * ARCHIVE_AFTER, a))
    assert _archive_old(kb, conn) == [a] and kb.get_task(conn, b).status == "done"
    print("subagents: ok")
    # crew.json: a real profile's running card counts; mirror cards (running sub b above) don't
    kb.create_task(conn, title="real", body="b", assignee="developer", created_by="default")
    real = conn.execute("SELECT id FROM tasks WHERE title = 'real'").fetchone()[0]
    with kb.write_txn(conn):
        conn.execute("UPDATE tasks SET status = 'running' WHERE id = ?", (real,))
        conn.execute("UPDATE tasks SET status = 'running' WHERE id = ?", (b,))  # mirror card, running
    p = Path(tempfile.mkdtemp()) / "crew.json"
    assert write_crew(conn, p, now=5) == {"running": 1, "blocked": 0, "ts": 5} == json.loads(p.read_text())
    print("crew: ok")


def _selftest_deliver(kb, conn):
    """Cursor logic: new vs delivered, own receipts skipped, busy waits, no agent -> receipt."""
    a = _new_card(kb, conn, "claude-code in x", "herdr-x", "b", "herdr-agent:t9")
    sent, busy = [], [True]
    send = lambda addr, text: (not busy[0]) and sent.append((addr, text)) is None
    m = {"agents": {"t9": {"card": a}}, "tasks": {}}
    kb.add_comment(conn, a, "chris", "Reply with the word PONG only.")
    kb.add_comment(conn, a, "chris", "Delivered to t9 at noon")  # receipt-shaped: skipped
    _deliver(kb, conn, m, send, lambda: "T")
    assert sent == [] and "cursor" not in m["agents"]["t9"]  # busy: still pending
    busy[0] = False
    _deliver(kb, conn, m, send, lambda: "T")
    _deliver(kb, conn, m, send, lambda: "T")  # nothing new: no resend
    assert sent == [("t9", "Reply with the word PONG only.")], sent
    bodies = [c.body for c in kb.list_comments(conn, a)]
    assert bodies.count("Delivered to t9 at T") == 1, bodies
    kb.add_comment(conn, a, "chris", "second")
    _deliver(kb, conn, m, send, lambda: "T")
    assert sent[-1] == ("t9", "second") and len(sent) == 2
    assert pending(kb.list_comments(conn, a), m["agents"]["t9"]["cursor"]) == []
    # Part A card with no live agent: receipt, cursor advances, nothing sent
    b = _new_card(kb, conn, "HMS-2: t", "herdr-x", "b", "herdr-task:k2")
    kb.add_comment(conn, b, "chris", "hi")
    m2 = {"tasks": {"k2": {"card": b}}}
    global _task_agent
    real, _task_agent = _task_agent, lambda key, folder: None
    try:
        _deliver(kb, conn, m2, send, lambda: "T")
        _deliver(kb, conn, m2, send, lambda: "T")
    finally:
        _task_agent = real
    bodies = [c.body for c in kb.list_comments(conn, b)]
    assert bodies == ["hi", "Not delivered: no agent is running this Herdr task"] and len(sent) == 2, bodies
    assert m2["tasks"]["k2"]["cursor"] == kb.list_comments(conn, b)[0].id
    print("deliver: ok")


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        _selftest()
