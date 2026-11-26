#!/usr/bin/env python3
"""Claude Code hook: list running subagents as labels on this Herdr terminal.

PreToolUse  (Agent|Task): hc label $HC_TERMINAL_ID muse.sub.<tool_use_id>=<description>
PostToolUse (Agent|Task): sync subagent -> clear muse.sub.<tool_use_id>.
                          async subagent (status async_launched, Claude's default) -> keep it and
                          record muse.agent.<agentId>=<tool_use_id>, since it is still running.
SubagentStop:             clear muse.agent.<agent_id> and the muse.sub.<tool_use_id> it points to.
One label per subagent, so parallel subagents never race on a shared value.
The herdr-panes Hermes plugin reads these labels with `hc get` (local and remote machines)
and keeps one kanban card per subagent. hc talks to this machine's herdr-core, so vast works the same.
Never blocks the tool: always exits 0, silent. No hc or no HC_TERMINAL_ID -> does nothing.
# ponytail: a subagent that dies without SubagentStop keeps its label until the terminal ends.
"""
import json, os, shutil, subprocess, sys


def hc(*a):
    return subprocess.run(["hc", *a], stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10)


try:
    term = os.environ.get("HC_TERMINAL_ID")
    if term and shutil.which("hc"):
        d = json.load(sys.stdin)
        tid, ev = d.get("tool_use_id"), d.get("hook_event_name")
        if ev == "PreToolUse" and tid:
            ti = d.get("tool_input") or {}
            prompt = str(ti.get("prompt") or "").strip()
            val = (str(ti.get("description") or "").strip() or prompt.split("\n")[0] or "Claude subagent")[:80]
            hc("label", term, f"muse.sub.{tid}={val}")
        elif ev == "PostToolUse" and tid:
            r = d.get("tool_response") or {}
            if isinstance(r, dict) and r.get("status") == "async_launched" and r.get("agentId"):
                hc("label", term, f"muse.agent.{r['agentId']}={tid}")
            else:
                hc("label", term, f"muse.sub.{tid}=")
        elif ev == "SubagentStop" and d.get("agent_id"):
            key = f"muse.agent.{d['agent_id']}"
            sub = (json.loads(hc("get", term, "--json").stdout or "{}").get("labels") or {}).get(key)
            if sub:  # only async subagents have this label; sync ones were cleared by PostToolUse
                hc("label", term, f"muse.sub.{sub}=", f"{key}=")
except Exception:
    pass
sys.exit(0)
