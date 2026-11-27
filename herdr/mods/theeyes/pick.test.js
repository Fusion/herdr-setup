// bun test ./pick.test.js (from the mod folder): the mood rule order of the pure pick().
import { test, expect, mock } from "bun:test";
mock.module("gpui-kit", () => ({ View: class {}, div: () => null, PathBuilder: {} }));
mock.module("herdr", () => ({ home: () => "/x", agents: () => [], terminals: () => [], panes: () => [],
  focused: () => null, readTextFile: async () => null }));
const { pick } = await import("./main.js");

const now = 10_000, crew = (running, blocked) => ({ running, blocked, ts: now });
const mood = (st, c = null, last = now) => pick(null, st, c, now, last).mood;

test("fresh avatar.json beats everything", () => {
  expect(pick({ expr: "happy|like", ts: now - 5 }, ["error"], crew(1, 1), now, now)).toEqual({ mood: "happy", overlay: "like" });
  expect(pick({ expr: "laugh", ts: now - 5 }, ["blocked"], null, now, now)).toEqual({ mood: "curious", overlay: "question", oneShot: "laugh" });
  expect(pick({ expr: "happy", ts: now - 61 }, ["error"], null, now, now).mood).toBe("angry"); // stale file ignored
});
test("error beats blocked", () => expect(mood(["blocked", "error", "done"], crew(1, 1))).toBe("angry"));
test("blocked beats done", () => expect(pick(null, ["done", "blocked"], null, now, now)).toEqual({ mood: "curious", overlay: "question" }));
test("crew blocked -> curious", () => expect(mood(["done"], crew(0, 1))).toBe("curious"));
test("done beats working", () => expect(mood(["working", "done"], crew(1, 0))).toBe("happy"));
test("crew running -> thinking", () => expect(mood(["idle"], crew(2, 0))).toBe("thinking"));
test("agent working -> thinking", () => expect(mood(["working"])).toBe("thinking"));
test("stale crew.json is ignored", () => expect(mood([], { running: 3, blocked: 1, ts: now - 181 })).toBe("default"));
test("idle > 15 min -> tired, else default", () => {
  expect(mood(["idle"], crew(0, 0), now - 901)).toBe("tired");
  expect(mood(["idle"], crew(0, 0), now - 899)).toBe("default");
});
