// hc-pick (Cmd+Shift+H): a popup listing live hc terminals, agents first.
// Type to filter, ↑/↓ to move, Enter puts `hc <address> (<space> / <tab>, <agent>, "<pane>", "<title>")`
// into the terminal that had focus (no Enter pressed), Esc closes.
// Herdr has no "type text" command, so Enter goes through the clipboard:
// pbcopy the text, terminal.paste, then put the old clipboard text back.

import { View, div } from "gpui-kit";
import { v_flex, h_flex, InputState, Input, ScrollHandle } from "gpui-base";
import { terminals, spaces, panes, focused, exec, run, theme, props, closeOverlay, checking, nextCommand } from "herdr";
import { refText, order, agentOf, statusOf, whereOf, paneNameOf, titleOf } from "./ref.js";

export default class HcPick extends View {
  init(_props, cx) {
    this.target = focused()?.terminal ?? null; // where Enter will paste
    this.filter = "";
    this.at = 0;
    this.busy = false;
    this.handle = cx.focus_handle();
    this.scroll = ScrollHandle.new();
    this.input = InputState.new({ placeholder: "Filter terminals: agent, space, tab, name, title, address…" });
    this.input.on("change", (_e, cx) => { this.filter = this.input.value(); this.at = 0; cx.notify(); });
    this.input.on("submit", (_e, cx) => this.pick(this.rows()[this.at], cx));
    if (checking()) return;
    this.input.focus();
    cx.timer.after(600, () => this.input.focus());
    // `herdr-app do hc-pick.enter` (or .down/.up): the same as the keys, for scripts and tests.
    cx.spawn(async (cx) => {
      for (;;) {
        const c = await nextCommand(), n = this.rows().length || 1;
        if (c === "enter") this.pick(this.rows()[this.at], cx);
        else if (c === "down") this.at = (this.at + 1) % n;
        else if (c === "up") this.at = (this.at + n - 1) % n;
        cx.notify();
      }
    });
  }

  close() {
    closeOverlay(props().overlay);
  }

  rows() {
    const sp = spaces(), pn = panes();
    const f = this.filter.toLowerCase();
    return order(terminals(), [this.target]).map((t) => ({
      t,
      app: agentOf(t),
      status: statusOf(t),
      where: whereOf(t, sp),
      name: paneNameOf(t, pn),
      title: titleOf(t, pn),
      text: refText(t, sp, pn),
    })).filter((r) => !f || r.text.toLowerCase().includes(f));
  }

  pick(r, cx) {
    if (!r || this.busy) return;
    if (!this.target) return this.close();
    this.busy = true;
    cx.spawn(async (cx) => {
      try {
        // ponytail: only text clipboards are restored; an image on the clipboard is lost.
        const prev = (await exec("pbpaste", [])).stdout;
        await exec("sh", ["-c", 'printf %s "$1" | pbcopy', "sh", r.text]);
        run("terminal.paste"); // the popup holds the keyboard, so this pastes into the focused pane
        await cx.sleep(300);
        if (prev) await exec("sh", ["-c", 'printf %s "$1" | pbcopy', "sh", prev]);
      } finally {
        this.close();
      }
    });
  }

  render() {
    const t = theme();
    const rows = this.rows();
    this.at = Math.max(0, Math.min(this.at, rows.length - 1));
    const glyph = (st) =>
      div().w(12).flex_none().text_color(t[st] ?? t.dim).child(st === "idle" ? "○" : st ? "●" : "·");
    const row = (r, i) =>
      h_flex().id(`hp-${r.t.address}`).mx(4).px(10).h(30).flex_none().rounded(7).gap(10).items_center().cursor_pointer()
        .when(i === this.at, (el) => el.bg(t.hover))
        .hover((s) => s.bg(t.hover))
        .on_click((_e, cx) => this.pick(r, cx))
        .child(glyph(r.status))
        .child(div().w(64).flex_none().text_size(11).text_color(t[r.status] ?? t.dim).child(r.status ?? ""))
        .child(div().w(92).flex_none().truncate().text_color(r.app ? t.foreground : t.dim).child(r.app ?? "terminal"))
        .child(div().flex_1().truncate().text_color(t.muted).child(r.where ?? ""))
        .child(div().w(220).flex_none().truncate().text_color(t.foreground).child([r.name, r.title !== r.name && r.title].filter(Boolean).map((x) => `"${x}"`).join(" ")))
        .child(div().w(96).flex_none().truncate().text_size(12).text_color(t.accent).child(r.t.address));

    return v_flex()
      .id("hc-pick")
      .track_focus(this.handle)
      .w_full()
      .min_h(0)
      .p(18)
      .gap(10)
      .bg(t.popover)
      .text_size(13)
      .on_key_down((e, cx) => {
        const k = e.key, n = rows.length || 1;
        if (k === "escape") return this.close();
        if (k === "down") this.at = (this.at + 1) % n;
        else if (k === "up") this.at = (this.at + n - 1) % n;
        else return;
        this.scroll.scroll_to_item(this.at);
        cx.stop_propagation();
        cx.notify();
      })
      .child(h_flex().items_center()
        .child(div().flex_1().text_size(15).font_semibold().text_color(t.foreground).child("Insert an hc reference"))
        .child(div().text_size(11).text_color(t.dim).child(this.target ? `into ${this.target} · Esc` : "no focused terminal · Esc")))
      .child(h_flex().h(36).flex_none().px(10).items_center().rounded(9).border_1().border_color(t.accent).bg(t.background)
        .child(Input.new(this.input).flex_1().h_full().text_size(12.8).text_color(t.foreground)))
      .child(div().text_size(11.5).text_color(t.dim).truncate().child(rows[this.at]?.text ?? "no terminals match"))
      // A popup sizes to its content, so the list needs a definite height (as the picker does).
      .child(v_flex().id("hp-list").h(Math.min(420, rows.length * 30)).flex_none().overflow_y_scrollbar().track_scroll(this.scroll)
        .children(rows.map(row)));
  }
}
