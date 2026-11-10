// The kittymux client's rules (client/lib/logic.js) under node, as they ship to QML: the file is loaded as is, minus QML's `.pragma`.
// Run by tests/test_client_logic.py; prints "ok N" and exits non-zero on the first failure.
import { readFileSync } from "node:fs";
import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const src = readFileSync(join(here, "..", "client", "lib", "logic.js"), "utf8").replace(/^\.pragma library\s*$/m, "");
const L = new Function(src + "\nreturn { STATE_GROUPS, asks, tone, tabsOf, sections, age, agentName, title, stateWord, detail, percent, header, step, jumpArgs, muteArgs, matchClient, placement, eventMoves };")();

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
    assert.deepEqual(L.muteArgs("km", t, false), ["km", "mute", "--pid", "7", "--window", "31"]);   // the pending state decides: a second click undoes
    const odd = L.sections(L.tabsOf(doc([tab(5, { project: "constructor" }), tab(6, { project: "toString" })])), false);
    assert.deepEqual(odd.map(s => s.label), ["constructor", "toString"]);    // no inherited properties in the project table
});

// Real-shaped Hyprland data (numbers made up): a laptop panel at scale 4/3 below-left of an external monitor.
const MONS = [{ id: 0, name: "DP-3", x: 1920, y: 0, width: 2560, height: 1440, scale: 1, activeWorkspace: { id: 12 }, specialWorkspace: { id: 0, name: "" } },
              { id: 1, name: "eDP-1", x: 0, y: 360, width: 2560, height: 1440, scale: 1.3333334, activeWorkspace: { id: 2 }, specialWorkspace: { id: 0, name: "" } }];
const KWIN = { kitty_pid: 4349, title: "~", geometry: { vw: 2512, vh: 1357, width: 1884, height: 1018, scale: 1.3333, edge: "left",
                                                        bar: [0, 0, 400, 1357], cell: [16, 34], opacity: 0.9 } };
const KC = { address: "0xk", pid: 4349, title: "~", at: [18, 409], size: [1884, 1018], workspace: { id: 2 }, monitor: 1, floating: false,
             fullscreen: 0, mapped: true, hidden: false, focusHistoryID: 0 };

test("the overlay sits on kitty's bar, minus the divider, in the monitor's logical pixels", () => {
    const p = L.placement(KWIN, [KC], MONS);
    assert.equal(p.visible, true);
    assert.equal(p.monitor, "eDP-1");
    assert.deepEqual([p.x, p.y], [18, 49]);                                   // 409 - 360
    assert.equal(p.w, Math.round((400 - 32) / 1.3333));                       // two divider cells stay kitty's
    assert.equal(p.h, 1018);
    const right = L.placement({ ...KWIN, geometry: { ...KWIN.geometry, edge: "right", bar: [2112, 0, 2512, 1357] } }, [KC], MONS);
    assert.equal(right.x, Math.round(18 + (2112 + 32) / 1.3333));             // on the right edge the divider is the bar's first columns
});

test("it hides when the bar is not what you see", () => {
    assert.equal(L.placement(KWIN, [{ ...KC, workspace: { id: 3 } }], MONS).reason, "another workspace");
    assert.equal(L.placement(KWIN, [KC, { address: "0xf", pid: 9, workspace: { id: 2 }, fullscreen: 2, at: [0, 360], size: [1920, 1080] }], MONS).reason,
                 "fullscreen window");
    const floater = { address: "0xp", pid: 9, workspace: { id: 2 }, floating: true, at: [100, 500], size: [300, 200] };
    assert.equal(L.placement(KWIN, [KC, floater], MONS).reason, "a floating window covers the bar");
    assert.equal(L.placement(KWIN, [KC, { ...floater, at: [900, 500] }], MONS).visible, true);       // beside the bar: no matter
    assert.equal(L.placement(KWIN, [{ ...KC, floating: true, focusHistoryID: 0 }, floater], MONS).visible, true);   // kitty on top
    assert.equal(L.placement({ ...KWIN, geometry: { ...KWIN.geometry, edge: "bottom" } }, [KC], MONS).reason, "no vertical bar");
    assert.equal(L.placement(KWIN, [], MONS).reason, "window not found");
    assert.equal(L.placement(KWIN, [{ ...KC, workspace: { id: 7 } }],
                             [MONS[0], { ...MONS[1], specialWorkspace: { id: 7, name: "special:term" } }]).visible, true);
});

test("several windows of one kitty: the one whose title and size match", () => {
    const other = { ...KC, address: "0xo", title: "htop", size: [900, 600] };
    assert.equal(L.matchClient(KWIN, [other, KC]).address, "0xk");
    assert.equal(L.matchClient(KWIN, [{ ...KC, pid: 1 }]), null);
});

test("only events that move windows hide the overlay while they animate", () => {
    assert.equal(L.eventMoves("workspacev2>>3,3"), true);
    assert.equal(L.eventMoves("movewindowv2>>0xk,2,2"), true);
    assert.equal(L.eventMoves("activewindowv2>>0xk"), false);
    assert.equal(L.eventMoves("windowtitlev2>>0xk,~"), false);
});

console.log("ok " + n);
