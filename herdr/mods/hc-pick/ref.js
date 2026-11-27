// Pure helpers for hc-pick (no herdr imports, so `bun test` can load them).

const STATUS = { blocked: 0, working: 1, done: 2, idle: 3 };
const APPS = ["claude-code", "codex", "hermes"];

// The agent a terminal reports (OSC 7501 app), else null. Plain shells have none.
export function agentOf(t) {
  return t.report?.app ?? (typeof t.status === "object" ? t.status?.app : null) ?? null;
}

// Status as a word: terminals() gives a word, `hc get --json` an object.
export function statusOf(t) {
  return typeof t.status === "object" ? (t.status?.state ?? null) : (t.status ?? null);
}

// "Space / Tab" from the live spaces list; the core's `where` label if the tab isn't there.
export function whereOf(t, spaces = []) {
  const tab = t.labels?.["herdr.tab"];
  const machine = t.address.includes("/") ? t.address.split("/")[0] : null;
  if (tab) {
    for (const s of spaces) {
      const hit = s.tabs?.find((x) => x.id === tab || x.id === `${machine}/${tab}`);
      // A tab someone named shows that name; an unnamed one its number (spaces() TabInfo).
      if (hit) return `${s.name} / ${hit.named === false ? hit.index ?? hit.name : hit.name}`;
    }
  }
  return t.labels?.where ?? null;
}

// The pane's name: Shepherdr's label, else the Herdr pane name (pane.rename).
export function paneNameOf(t, panes = []) {
  return t.labels?.["shepherdr.name"] || panes.find((p) => p.terminal === t.address)?.name || null;
}

// Same as the tabs mod's label(): drop a status glyph, keep a leading bracket or quote.
const clean = (s) => (s ?? "").replace(/^[^\p{L}\p{N}\p{Ps}\p{Pi}]+/u, "").replace(/^\[ [!.] \] /, "").trim();

// The terminal's title (Claude sets it to its session title) when it tells something,
// by the tabs mod's rule: not empty, the address, the program, a path or a user@host prompt.
// `hc get` has `title`; terminals() follows `hc ls --json` (no title), so fall back to panes()' title.
export function titleOf(t, panes = []) {
  const p = panes.find((x) => x.terminal === t.address);
  const raw = t.title || p?.title || "", prog = t.program ?? p?.program;
  const live = clean(raw);
  const path = /^[~/]|^[A-Za-z]:\\/.test(raw.replace(/^[^\p{L}\p{N}~/]+/u, ""));
  const progs = [agentOf(t), prog?.name, prog?.key].filter(Boolean).map((x) => x.toLowerCase());
  return live && live !== t.address && !progs.includes(live.toLowerCase()) && !path && !live.includes("@") ? live : null;
}

// `hc <address> (<space> / <tab>, <agent>, "<pane name>", "<title>")`, leaving out what's missing.
// The tab part is spaces()' tab name: the given name when `named`, else its number (herdr.d.ts).
export function refText(t, spaces = [], panes = []) {
  const name = paneNameOf(t, panes), title = titleOf(t, panes);
  const parts = [whereOf(t, spaces), agentOf(t), name && `"${name}"`, title && title !== name && `"${title}"`].filter(Boolean);
  return parts.length ? `hc ${t.address} (${parts.join(", ")})` : `hc ${t.address}`;
}

// Live terminals only, agents first (by status, then claude-code, codex, hermes), then the rest.
export function order(terminals, skip = []) {
  const rank = (t) => {
    const app = agentOf(t);
    if (!app) return [1, 0, 0];
    const a = APPS.indexOf(app);
    return [0, STATUS[statusOf(t)] ?? 4, a < 0 ? APPS.length : a];
  };
  return terminals
    .filter((t) => t.state === "live" && !skip.includes(t.address))
    .map((t) => [rank(t), t])
    .sort(([a, x], [b, y]) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2] || x.address.localeCompare(y.address, undefined, { numeric: true }))
    .map(([, t]) => t);
}
