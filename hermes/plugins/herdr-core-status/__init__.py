"""local: tells Herdr core what Hermes is doing (OSC 7501), as Claude Code and Codex do, so Shepherdr shows
it working (chat spinner, sidebar dot), blocked on a permission or question, and idle.

Herdr core reads OSC 7501 records from what a terminal prints: ESC ] 7501 ; state=<s>:app=hermes[:kind=...] BEL.
Hermes 0.23 runs turns in its gateway process, which has no terminal, so a hook finds the CLI process that shows
the session (~/.hermes/runtime/active_sessions.json: pid and started_at; the database's session row started
within moments of it) and writes the record to that process's tty. Herdr's own herdr-agent-state plugin only
speaks to the classic herdr (HERDR_PANE_ID).
"""
from __future__ import annotations

import base64
import json
import os
import sqlite3
import subprocess

_HOME = os.environ.get("HERMES_HOME") or os.path.expanduser("~/.hermes")
_ROOT = os.path.expanduser("~/.hermes")


# The tty of the CLI showing a session now: looked up each time (no cache), as a resumed session moves terminals.
def _tty_of(session_id: str) -> str | None:
    try:
        entries = json.load(open(os.path.join(_ROOT, "runtime", "active_sessions.json"))).get("entries", [])
    except (OSError, ValueError):
        entries = []
    # Hermes 0.23 names the database's session id in the registry: exact.
    exact = [e for e in entries if session_id in (e.get("session_id"), (e.get("metadata") or {}).get("live_session_id"))]
    if exact:
        return _remember(session_id, str(exact[-1].get("pid")))
    try:
        con = sqlite3.connect(f"file:{os.path.join(_HOME, 'state.db')}?mode=ro", uri=True, timeout=1)
        row = con.execute("select started_at from sessions where id=?", (session_id,)).fetchone()
        con.close()
        entries = json.load(open(os.path.join(_ROOT, "runtime", "active_sessions.json"))).get("entries", [])
    except (OSError, ValueError, sqlite3.Error):
        return None
    if not row:
        return None
    # shortcut: matched by start time (10 s), as core/hermes.js FIND does; two CLIs started together could swap.
    near = [e for e in entries if abs(float(e.get("started_at") or 0) - row[0]) < 10]
    if not near:
        return None
    return _remember(session_id, str(min(near, key=lambda e: abs(float(e.get("started_at") or 0) - row[0])).get("pid")))


def _remember(session_id: str, pid: str) -> str | None:
    tty = subprocess.run(["ps", "-o", "tty=", "-p", pid], capture_output=True, text=True).stdout.strip()
    if not tty or tty in ("?", "??"):
        return None
    return f"/dev/{tty}"


def _clip(s, n=60) -> str:
    s = " ".join(str(s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


# What a tool call is doing, in the chat's working line (Claude Code reports the same: "Running npm test").
def _doing(name: str, a: dict) -> str:
    a = a if isinstance(a, dict) else {}
    path = os.path.basename(str(a.get("path") or a.get("file_path") or ""))
    if name == "terminal":
        return "Running " + _clip(a.get("command"), 50)
    if name == "execute_code":
        return "Running a script"
    if name == "read_file":
        return f"Reading {path}"
    if name in ("write_file", "patch"):
        return f"Editing {path}"
    if name in ("search_files", "session_search"):
        return "Searching " + _clip(a.get("pattern") or a.get("query"), 40)
    if name == "web_search":
        return "Searching the web: " + _clip(a.get("query"), 40)
    if name == "web_extract" or name.startswith("browser_"):
        return "Reading the web"
    if "hindsight" in name or name == "memory":
        return "Searching memory" if "recall" in name or "search" in name or name == "memory" else "Using memory"
    if name == "delegate_task":
        return "Starting a helper"
    return f"Using {name}"


_last = {"sid": ""}  # the session the latest hook named, for a hook that names none
_live: dict[str, str | None] = {}  # session id -> turn_id of its turn in progress (see _say)
# Debug trace, off by default: HERDR_STATUS_DEBUG=1 in the gateway's env. Lines: time hook state sid tty extra.
_DEBUG = os.path.expanduser("~/Tmp/the-muse/data/herdr-status-debug.log")


def _debug(*parts) -> None:
    if os.environ.get("HERDR_STATUS_DEBUG") == "1":
        import time
        with open(_DEBUG, "a") as f:
            f.write(" ".join(map(str, (f"{time.time():.3f}", *parts))) + "\n")


# kw: the hook's own arguments, as one dict (some hooks pass their own `kind`).
def _say(state: str, block: str | None, msg: str | None, kw: dict) -> None:
    sid = kw.get("session_id")
    if isinstance(sid, str) and sid:
        _last["sid"] = sid
    else:
        sid = _last["sid"]
    if not sid:
        return
    kind = block
    hook, turn = kw.get("_hook"), kw.get("turn_id")
    # Only the live turn may say working/blocked. The post-turn background review fork shares the session id
    # and fires pre_api_request/tool hooks AFTER post_llm_call, but never pre_llm_call or post_llm_call, so
    # without this the robot stays "working" until the next turn. A live turn opens at pre_llm_call and
    # closes at post_llm_call / on_session_end; a hook from any other turn_id is the fork: dropped.
    if hook == "pre_llm_call":
        _live[sid] = turn
    elif state in ("idle", "error"):
        _live.pop(sid, None)
    elif sid not in _live or (turn and turn != _live[sid]):
        _debug(hook, state, sid, "-", f"turn={turn}", "dropped")
        return
    tty = _tty_of(sid)
    _debug(hook, state, sid, tty, f"turn={turn}")
    if not tty:
        return
    rec = f"state={state}:app=hermes" + (f":kind={kind}" if kind else "")
    if msg:
        # msg is base64 (UTF-8) in the record, like OSC 52's text.
        rec += ":msg=" + base64.b64encode("".join(c for c in msg if c.isprintable()).encode()).decode()
    try:
        with open(tty, "w") as t:
            t.write(f"\033]7501;{rec}\007")
    except OSError:
        pass


# A CLI opened its session: idle, so Herdr (hc run's first message, hc wait) sees Hermes ready before any turn.
# The registry entry naming the CLI's tty may land a moment after the open: a few tries (this runs on its own thread).
def _opened(kw: dict) -> None:
    import time
    sid = kw.get("session_id")
    for _ in range(10):
        if isinstance(sid, str) and sid and _tty_of(sid):
            _say("idle", None, None, kw)
            return
        time.sleep(0.5)


def register(ctx):
    on = lambda hook, state, block=None, msg=None: ctx.register_hook(hook, lambda **kw: _say(state, block, msg, {**kw, "_hook": hook}))
    ctx.register_hook("on_session_open", lambda **kw: _opened(kw))
    on("pre_llm_call", "working", msg="Thinking")  # a turn starts
    on("pre_api_request", "working", msg="Thinking")
    on("post_tool_call", "working", msg="Thinking")
    ctx.register_hook("pre_tool_call", lambda **kw: _say("working", None, _doing(str(kw.get("tool_name") or ""), kw.get("args")), {**kw, "_hook": "pre_tool_call"}))
    on("post_llm_call", "idle")                   # once per turn, at its end
    on("pre_approval_request", "blocked", "permission")
    on("post_approval_response", "working")
    # A clarify question waits on the person; a sudo password or a dangerous command is a permission.
    ctx.register_hook("on_human_input_request", lambda **kw: _say("blocked", "question" if kw.get("kind") == "clarify" else "permission",
                                                                  "Asking you something" if kw.get("kind") == "clarify" else "Waiting for your approval", kw))
    on("on_human_input_resolved", "working", msg="Thinking")
    # Fires at every turn's end with how it went: a failed turn (not one you stopped) is an error,
    # which Herdr shows as needing you and the sidebar as a red dot.
    ctx.register_hook("on_session_end", lambda **kw: _say("error", None, "The turn failed", {**kw, "_hook": "on_session_end"})
                      if kw.get("failed") and not kw.get("interrupted") else _say("idle", None, None, {**kw, "_hook": "on_session_end"}))


# Self-check: python3 __init__.py. One live turn with a tool call, then the background review fork's hooks
# (same session, its own turn_id): the tty's last record must be idle.
if __name__ == "__main__":
    import tempfile
    tty = tempfile.NamedTemporaryFile("r", suffix=".tty")
    _tty_of = lambda sid: tty.name  # noqa: F811
    _DEBUG = "/nonexistent"  # noqa: F811
    hooks = {}
    register(type("Ctx", (), {"register_hook": lambda self, h, fn: hooks.__setitem__(h, fn)})())
    live, fork = dict(session_id="s1", turn_id="s1:a"), dict(session_id="s1", turn_id="s1:b")
    last = lambda: (tty.seek(0), tty.read().rsplit("\033]7501;", 1)[-1])[1]  # each write reopens "w": one record
    for h, kw in [("pre_llm_call", live), ("pre_api_request", live), ("pre_tool_call", {**live, "tool_name": "terminal"})]:
        hooks[h](**kw)
    assert last().startswith("state=working"), last()  # the live turn says working
    for h, kw in [("post_tool_call", live), ("pre_api_request", live), ("post_llm_call", live), ("on_session_end", live),
                  ("pre_api_request", fork), ("pre_tool_call", {**fork, "tool_name": "memory"}), ("post_tool_call", fork)]:
        hooks[h](**kw)
    assert last().startswith("state=idle"), last()  # ...and the fork after it can't flip it back
    print("ok: mid-turn working, last record after the fork =", repr(last()))
