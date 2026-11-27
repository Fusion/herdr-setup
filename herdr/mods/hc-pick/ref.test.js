import { test, expect } from "bun:test";
import { refText, order, titleOf } from "./ref.js";

const spaces = [
  { name: "Work In Progress", tabs: [{ id: "tb1", name: "2" }] },
  { name: "amd-ml", tabs: [{ id: "vast/tb9", name: "2" }] },
];

test("local terminal", () => {
  const t = { address: "t86", state: "live", status: "done", report: { app: "claude-code" }, labels: { "herdr.tab": "tb1" } };
  expect(refText(t, spaces)).toBe("hc t86 (Work In Progress / 2, claude-code)");
});

test("remote terminal: tab id carries the machine prefix in spaces()", () => {
  const t = { address: "vast/t2", state: "live", report: { app: "claude-code" }, labels: { "herdr.tab": "tb9" } };
  expect(refText(t, spaces)).toBe("hc vast/t2 (amd-ml / 2, claude-code)");
});

test("pane name: shepherdr label, else Herdr pane name", () => {
  const t = { address: "t86", report: { app: "claude-code" }, labels: { "herdr.tab": "tb1", "shepherdr.name": "fix login" } };
  expect(refText(t, spaces)).toBe('hc t86 (Work In Progress / 2, claude-code, "fix login")');
  const u = { address: "t86", report: { app: "claude-code" }, labels: { "herdr.tab": "tb1" } };
  expect(refText(u, spaces, [{ terminal: "t86", name: "db" }])).toBe('hc t86 (Work In Progress / 2, claude-code, "db")');
});

test("missing agent, missing tab, nothing at all: no 'undefined'", () => {
  expect(refText({ address: "t9", labels: { "herdr.tab": "tb1" } }, spaces)).toBe("hc t9 (Work In Progress / 2)");
  expect(refText({ address: "t9", labels: { where: "Home / 2" } }, [])).toBe("hc t9 (Home / 2)");
  expect(refText({ address: "t9" }, spaces)).toBe("hc t9");
  expect(refText({ address: "t9", report: { app: "codex" } })).toBe("hc t9 (codex)");
});

test("order: agents by status then app, then the rest; drops non-live and skipped", () => {
  const ts = [
    { address: "t1", state: "live" },
    { address: "t2", state: "live", status: "idle", report: { app: "claude-code" } },
    { address: "t3", state: "live", status: "blocked", report: { app: "hermes" } },
    { address: "t4", state: "live", status: "working", report: { app: "codex" } },
    { address: "t5", state: "live", status: "working", report: { app: "claude-code" } },
    { address: "t6", state: "exited", status: "blocked", report: { app: "claude-code" } },
    { address: "t7", state: "live", status: "done", report: { app: "claude-code" } },
    { address: "t8", state: "live" },
  ];
  expect(order(ts, ["t8"]).map((t) => t.address)).toEqual(["t3", "t5", "t4", "t7", "t2", "t1"]);
});

test("telling title goes last; pane name first when it differs", () => {
  const t = { address: "t86", report: { app: "claude-code" }, title: "✳ NETBIRD-GITHUB-HANDOFF.md", labels: { "herdr.tab": "tb1" } };
  expect(refText(t, spaces)).toBe('hc t86 (Work In Progress / 2, claude-code, "NETBIRD-GITHUB-HANDOFF.md")');
  const n = { ...t, labels: { ...t.labels, "shepherdr.name": "netbird" } };
  expect(refText(n, spaces)).toBe('hc t86 (Work In Progress / 2, claude-code, "netbird", "NETBIRD-GITHUB-HANDOFF.md")');
  expect(refText({ ...n, title: "netbird" }, spaces)).toBe('hc t86 (Work In Progress / 2, claude-code, "netbird")');
});

test("titles that tell nothing are skipped (path, address, program, user@host, empty)", () => {
  const base = { address: "t9", report: { app: "claude-code" }, program: { name: "Claude Code", key: "claude" } };
  for (const title of ["", "~/Projects/x", "/usr/bin", "⠂ ~/x", "t9", "claude-code", "Claude Code", "claude", "chris@mbp : Home_WIP", undefined])
    expect(titleOf({ ...base, title })).toBe(null);
  expect(refText({ ...base, title: "/tmp" })).toBe("hc t9 (claude-code)");
});

test("named tab shows its name, unnamed tab its number (local and remote)", () => {
  // spaces() shape (herdr.d.ts TabInfo): an unnamed tab's name is its number, named=false.
  const sp = [
    { name: "WIP", machine: null, tabs: [{ id: "tbA", index: 1, name: "sheepdog", named: true }, { id: "tbB", index: 2, name: "2", named: false }] },
    { name: "amd-ml", machine: "vast", tabs: [{ id: "vast/tbC", index: 1, name: "train", named: true }, { id: "vast/tbD", index: 2, name: "2", named: false }] },
  ];
  const w = (address, tab) => refText({ address, labels: { "herdr.tab": tab, where: "stale / 9" } }, sp);
  expect(w("t1", "tbA")).toBe("hc t1 (WIP / sheepdog)");
  expect(w("t2", "tbB")).toBe("hc t2 (WIP / 2)");
  expect(w("vast/t3", "tbC")).toBe("hc vast/t3 (amd-ml / train)");
  expect(w("vast/t4", "tbD")).toBe("hc vast/t4 (amd-ml / 2)");
});

test("title from panes() when terminals() has none (live mod shape)", () => {
  const t = { address: "t86", report: { app: "claude-code" }, labels: { "herdr.tab": "tb1" } };
  const pn = [{ terminal: "t86", name: null, title: "✳ NETBIRD-GITHUB-HANDOFF.md", program: { name: "Claude Code", key: "claude" } }];
  expect(refText(t, spaces, pn)).toBe('hc t86 (Work In Progress / 2, claude-code, "NETBIRD-GITHUB-HANDOFF.md")');
  expect(titleOf(t, [{ ...pn[0], title: "Claude Code" }])).toBe(null);
});
