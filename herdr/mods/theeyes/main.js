// theeyes: the Unity robot eyes (theeyes/Assets/Scripts/Avatar.cs) redrawn natively.
// Mood: ~/Tmp/the-muse/data/avatar.json (written by avatar_set_expression) when < 60 s old,
// else the focused tab's agent status. Motion is native (transition/loop); timers only for
// the file poll, glances and blinks.
import { View, div, PathBuilder } from "gpui-kit";
import { home, focused, spaces, readTextFile } from "herdr";

const BG = "#0b0f14", EYE = "#3cf2ff", PINK = "#ff5ca8", DROP = "#99e6ff";
const EYE_W = 70, EYE_H = 70, GAP = 34, RAD = 18, PAD = 12; // 320x200 virtual canvas, as in Avatar.cs
const MOODS = ["default", "happy", "tired", "angry", "thinking", "curious"];
const ONE_SHOT_MS = { laugh: 1200, confused: 800, sweat: 3000 };
const FRESH_S = 60;
const FILE = `${home()}/Tmp/the-muse/data/avatar.json`;

// Agent status of the focused tab -> expression (blocked > done > working > idle, Herdr's own rollup).
export function statusExpr(status) {
  return { working: "thinking", blocked: "curious|question", done: "happy" }[status] ?? "default";
}

// Pure: which expression to show. file = parsed avatar.json or null; now in seconds.
export function pick(file, status, now) {
  const fresh = file && typeof file.expr === "string" && now - Number(file.ts) < FRESH_S;
  const [m, o = "none"] = (fresh ? file.expr : statusExpr(status)).split("|");
  if (MOODS.includes(m)) return { mood: m, overlay: o };
  return { ...pick(null, status, now), oneShot: m in ONE_SHOT_MS ? m : null }; // one-shot over the status mood
}

const rand = (a, b) => a + Math.random() * (b - a);

export default class TheEyes extends View {
  init(_props, cx) {
    this.size = { width: 268, height: 140 };
    this.file = null;
    this.played = 0;        // ts of the last one-shot played, so it plays once
    this.oneShot = null;
    this.look = { x: 0, y: 0 };
    this.closed = false;
    this.glanceAt = 0;
    // ponytail: 1 s poll of a tiny file; switch to watchFolder(~/Tmp/the-muse/data) if latency matters.
    cx.timer.every(1000, (cx) => this.poll(cx));
    this.poll(cx);
    this.blink(cx);
  }

  poll(cx) {
    cx.spawn(async (cx) => {
      let file = null;
      try { file = JSON.parse((await readTextFile(FILE)) ?? "null"); } catch { file = null; }
      this.file = file;
      const shot = typeof file?.expr === "string" && Date.now() / 1000 - Number(file.ts) < FRESH_S ? file.expr.split("|")[0] : null;
      if (shot in ONE_SHOT_MS && file.ts !== this.played) {
        this.played = file.ts;
        this.oneShot = shot;
        cx.timer.after(ONE_SHOT_MS[shot], (cx) => { this.oneShot = null; cx.notify(); });
      }
      if (Date.now() > this.glanceAt) { // idle glance, as in Avatar.cs
        this.glanceAt = Date.now() + rand(1500, 4000);
        this.look = { x: rand(-28, 28), y: rand(-12, 12) };
      }
      cx.notify();
    });
  }

  blink(cx) {
    cx.timer.after(rand(2000, 5000), (cx) => {
      this.closed = true; cx.notify();
      cx.timer.after(120, (cx) => { this.closed = false; cx.notify(); this.blink(cx); });
    });
  }

  render() {
    const f = focused();
    const tab = f && spaces().flatMap((s) => s.tabs).find((t) => t.id === f.tab);
    const { mood, overlay } = pick(this.file, tab?.status ?? null, Date.now() / 1000);
    const oneShot = this.oneShot;

    const { width: W, height: H } = this.size, s = Math.min(W / 320, H / 200);
    let { x: lx, y: ly } = this.look;
    if (mood === "thinking") { lx = 14; ly = -28; }
    if (mood === "curious" && Math.abs(lx) < 10) lx = -28;

    // Group: both eyes plus lid padding, centered, moved by the look offset.
    const gw = (2 * EYE_W + GAP + 2 * PAD) * s, gh = (EYE_H + 14 + 2 * PAD) * s;
    const gx = W / 2 - gw / 2 + lx * s, gy = H / 2 - gh / 2 + ly * s;

    const eye = (left) => {
      let h = EYE_H;
      if (mood === "curious") h += (left ? lx < -10 : lx > 10) ? 14 : 0;
      if (this.closed) h = 4;
      const x = (PAD + (left ? 0 : EYE_W + GAP)) * s, w = EYE_W * s, y = gh / 2 - (h * s) / 2, hh = h * s;
      const r = Math.min(RAD * s, hh / 2);
      const glow = [2, 1].map((g) => div().id(`glow-${left}-${g}`).absolute()
        .left(x - g * 5 * s).top(y - g * 5 * s).w(w + 2 * g * 5 * s).h(hh + 2 * g * 5 * s)
        .rounded(r + g * 5 * s).bg(`${EYE}1a`).transition("height", 80).transition("top", 80));
      const body = div().id(`eye-${left}`).absolute().left(x).top(y).w(w).h(hh).rounded(r).bg(EYE)
        .transition("height", 80).transition("top", 80);
      // Lids in the background colour, over the eye (fixed to the open eye, like Avatar.cs).
      const top = gh / 2 - (EYE_H * s) / 2, p = PAD * s;
      const outer = left ? x - p : x + w + p, inner = left ? x + w + p : x - p;
      const lids = [];
      const tri = (pts) => window.paint_path(PathBuilder.fill().add_polygon(pts, true).build(), BG)
        .absolute().top(0).left(0).size_full();
      if (mood === "tired") lids.push(tri([[outer, top - p], [inner, top - p], [outer, top + EYE_H * 0.5 * s]]));
      if (mood === "angry") lids.push(tri([[outer, top - p], [inner, top - p], [inner, top + EYE_H * 0.5 * s]]));
      if (mood === "happy") lids.push(div().absolute().left(x - p).top(top + EYE_H * s - EYE_H * 0.55 * s)
        .w(w + 2 * p).h(EYE_H * s + p).rounded(r).bg(BG));
      return [...glow, body, ...lids];
    };

    const shaker = div().id("shaker").relative().size_full().children([...eye(true), ...eye(false)]);
    if (oneShot === "laugh") shaker.loop("top", { from: -5 * s, to: 5 * s, period: 130 });
    if (oneShot === "confused") shaker.loop("left", { from: -8 * s, to: 8 * s, period: 110 });

    const kids = [div().id("group").absolute().left(gx).top(gy).w(gw).h(gh)
      .transition("left", { duration: 250, easing: "ease-out" })
      .transition("top", { duration: 250, easing: "ease-out" }).child(shaker)];

    // Overlay above the eyes: heart (like) or question mark.
    const ox = W / 2 + lx * s, oy = H / 2 + (ly - 72) * s;
    if (overlay === "like") {
      const r = 16 * s, b = 4 * r; // heart path from Avatar.cs, in a b x b box centred on (ox, oy)
      const c = b / 2;
      const heart = PathBuilder.fill().move_to(c, c + r * 1.6)
        .cubic_bezier_to(c, c - r * 0.4, c - r * 2.2, c + r * 0.2, c - r * 1.2, c - r * 1.4)
        .cubic_bezier_to(c, c + r * 1.6, c + r * 1.2, c - r * 1.4, c + r * 2.2, c + r * 0.2).close().build();
      kids.push(div().id("ov-like").absolute().left(ox - c).top(oy - c).w(b).h(b)
        .transition("left", 250).transition("top", 250)
        .child(window.paint_path(heart, PINK).absolute().top(0).left(0).size_full()));
    } else if (overlay === "question") {
      const fs = 40 * s;
      kids.push(div().id("ov-q").absolute().left(ox - fs / 2).top(oy - fs * 0.7).w(fs).h(fs * 1.4)
        .flex().items_center().justify_center().text_size(fs).font_weight(900).text_color("#ffffff").child("?"));
    }
    if (oneShot === "sweat") {
      for (let i = 0; i < 3; i++) {
        const dx = W / 2 - (GAP / 2 + EYE_W + 14 + i * 10) * s + lx * s, dy = H / 2 + (ly - 46) * s;
        kids.push(div().id(`drop-${i}`).absolute().left(dx).top(dy).w(8 * s).h(12 * s).rounded(4 * s).bg(DROP)
          .loop("top", { from: dy, to: dy + 40 * s, period: 1250 + i * 200, easing: "ease-in" })
          .loop("opacity", { from: 1, to: 0, period: 1250 + i * 200 }));
      }
    }

    return div().id("root").relative().size_full().bg(BG).overflow_hidden()
      .on_size_change((size, cx) => { this.size = size; cx.notify(); })
      .children(kids);
  }
}
