// The kittymux client's rules (client/lib/logic.js) under node, as they ship to QML: the file is loaded as is, minus QML's `.pragma`.
// Run by tests/test_client_logic.py; prints "ok N" and exits non-zero on the first failure.
import { readFileSync } from "node:fs";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const src = readFileSync(join(here, "..", "client", "lib", "logic.js"), "utf8").replace(/^\.pragma library\s*$/m, "");
const L = new Function(src + "\nreturn { STATE_GROUPS, asks, tone, tabsOf, sections, age, agentName, title, stateWord, detail, percent, header, step, jumpArgs, muteArgs };")();

const tab = (id, extra = {}) => ({ tab_id: id, index: id, title: "t" + id, project: "calm-otter", state: "", panes: 1,
                                   action: { op: "jump", pid: 7, w: String(id) }, ...extra });
const doc = (tabs, pid = 7, focused = true) => ({ version: 1, windows: [{ kitty_pid: pid, os_window_id: 1, focused, palette: {}, tabs }] });
let n = 0;
const test = (name, fn) => { fn(); n++; };

test("the document's tabs, in the bar's order, each knowing its kitty", () => {
    const ts = L.tabsOf(doc([tab(1, { active: true }), tab(2)]));
    assert.deepEqual(ts.map(t => t.key), ["7.1", "7.2"]);
    assert.equal(ts[0].active, true);
    assert.equal(L.tabsOf({ version: 2, windows: [] }).length, 0);              // a schema it does not know: nothing, never a guess
    assert.equal(L.tabsOf(null).length, 0);
    assert.equal(L.tabsOf(doc([tab(1)]), { 7: false }).length, 0);            // a kitty that exited
});

test("active means the focused OS window's active tab only", () => {
    assert.equal(L.tabsOf(doc([tab(1, { active: true })], 7, false))[0].active, false);
});

test("by space keeps first-seen order; by state is Needs you, Working, Finished, Idle", () => {
    const ts = L.tabsOf(doc([tab(1, { state: "working" }), tab(2, { project: "quiet-heron", state: "done" }),
                             tab(3, { state: "waiting" }), tab(4, { state: "error" }), tab(5, { state: "idle" }), tab(6)]));
    assert.deepEqual(L.sections(ts, false).map(s => s.label), ["calm-otter", "quiet-heron"]);
    const by = L.sections(ts, true);
    assert.deepEqual(by.map(s => s.label), ["Needs you", "Working", "Finished", "Idle"]);
    assert.deepEqual(by[0].rows.map(t => t.tabId), [3, 4]);                   // error sits with needs you, as in the panel
    assert.deepEqual(by[3].rows.map(t => t.tabId), [5, 6]);
});

test("a muted agent never asks for you, and is drawn faint", () => {
    const t = L.tabsOf(doc([tab(1, { state: "waiting", muted: true })]))[0];
    assert.equal(L.asks(t), false);
    assert.equal(L.tone(t), "faint");
    assert.equal(L.header([t]).needsYou, 0);
    assert.equal(L.tone({ state: "waiting" }), "waiting");
    assert.equal(L.tone({ state: "done" }), "done");
    assert.equal(L.tone({ state: "error" }), "alert");
    assert.equal(L.tone({ state: "working" }), "text");                       // working moves, it does not shout
});

test("ages, percents and the second line", () => {
    assert.equal(L.age(1000, 1010), "<1m");
    assert.equal(L.age(1000, 1000 + 4 * 60), "4m");
    assert.equal(L.age(1000, 1000 + 3 * 3600), "3h");
    assert.equal(L.age(0, 5), "");
    assert.equal(L.percent({ state: "working", progress: 0.642 }), 64);
    assert.equal(L.percent({ state: "working", progress: null }), -1);
    assert.equal(L.percent({ state: "done", progress: 1 }), -1);
    assert.equal(L.detail({ state: "waiting", question: "Allow edit?" }, 0), "Allow edit?");
    assert.equal(L.detail({ state: "", branch: "main", cwd: "~/x" }, 0), "main");
    assert.equal(L.detail({ state: "limited", limitReset: 1000 + 600 }, 1000), "resets in 10m");
    assert.equal(L.stateWord({ state: "done" }), "Finished");
});

test("the header names where you are first", () => {
    const ts = L.tabsOf(doc([tab(1, { active: true, branch: "main" }), tab(2, { state: "waiting" })]));
    const h = L.header(ts);
    assert.equal(h.title, "calm-otter");
    assert.equal(h.subtitle, "main · 2 tabs");
    assert.equal(h.needsYou, 1);
    assert.equal(L.header([]).subtitle, "No kitty running");
});

test("keyboard steps clamp at the ends", () => {
    assert.equal(L.step(-1, 1, 3), 0);
    assert.equal(L.step(-1, -1, 3), 2);
    assert.equal(L.step(2, 1, 3), 2);
    assert.equal(L.step(0, -1, 3), 0);
    assert.equal(L.step(0, 1, 0), -1);
});

test("commands are argument lists for the row's own kitty, never a shell string", () => {
    const t = L.tabsOf(doc([tab(3, { agent: "claude", agent_window: 31, muted: true })]))[0];
    assert.deepEqual(L.jumpArgs("km", t), ["km", "act", '{"op":"jump","pid":7,"w":"3"}']);
    assert.deepEqual(L.muteArgs("km", t), ["km", "unmute", "--pid", "7", "--window", "31"]);
    assert.deepEqual(L.muteArgs("km", L.tabsOf(doc([tab(4)]))[0]), []);       // no agent in the tab: nothing to mute
});

console.log("ok " + n);
