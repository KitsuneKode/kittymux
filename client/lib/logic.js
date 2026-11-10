.pragma library
// The kittymux client's rules, pure (no QML types), so `node tests/client_logic.mjs` tests them as they ship.
// Inputs are tabs.json (version 1, docs/inbox.md); grouping mirrors the panel (kittymux_deck.STATE_GROUPS) so the two never disagree.

var STATE_GROUPS = [
    { label: "Needs you", states: ["waiting", "limited", "error"] },
    { label: "Working", states: ["working"] },
    { label: "Finished", states: ["done"] }
];
var IDLE_GROUP = "Idle";

// Does this tab ask for you? A muted one never does (kittymux_deck.asks).
function asks(t) {
    return (t.state === "waiting" || t.state === "limited") && !t.muted;
}

// The tone a state is drawn in: colour only for state. accent = where you are (not a state), orange = needs you,
// green = finished, red = error. Working is the text colour: it moves (the ring turns), it does not shout.
function tone(t) {
    if (t.muted) return "faint";
    if (t.state === "waiting" || t.state === "limited") return "waiting";
    if (t.state === "error") return "alert";
    if (t.state === "done") return "done";
    if (t.state === "working") return "text";
    return "faint";
}

// One flat list of tabs from the document: each carries its kitty and OS window, in the bar's order.
function tabsOf(doc, alive) {
    if (!doc || doc.version !== 1 || !Array.isArray(doc.windows)) return [];
    var out = [];
    for (var i = 0; i < doc.windows.length; i++) {
        var w = doc.windows[i];
        if (!w || !Array.isArray(w.tabs)) continue;
        if (alive && alive[w.kitty_pid] === false) continue;           // a kitty that exited and nobody pruned yet
        for (var j = 0; j < w.tabs.length; j++) {
            var t = w.tabs[j];
            if (!t || typeof t.tab_id !== "number") continue;
            out.push({
                key: w.kitty_pid + "." + t.tab_id, windowKey: String(w.key || ""),
                kittyPid: w.kitty_pid, osWindow: w.os_window_id, focusedWindow: !!w.focused,
                tabId: t.tab_id, index: t.index || j + 1, active: !!t.active && !!w.focused,
                activeInWindow: !!t.active,
                title: String(t.title || ""), cwd: String(t.cwd || ""), project: String(t.project || ""),
                branch: String(t.branch || ""), hue: /^#[0-9a-fA-F]{6}$/.test(t.hue || "") ? t.hue : "",
                panes: t.panes || 1, agent: String(t.agent || ""), agentWindow: t.agent_window, brand: String(t.brand || ""),
                state: String(t.state || ""), since: typeof t.since === "number" ? t.since : 0,
                progress: typeof t.progress === "number" ? t.progress : null,
                question: t.question ? String(t.question) : "", limitReset: t.limit_reset || 0,
                muted: !!t.muted, action: t.action || null, palette: w.palette || {}
            });
        }
    }
    return out;
}

// Sections for the list. By space: one per project in first-seen order (the bar's order). By state: Needs you → Working →
// Finished → Idle, each keeping the bar's order inside it. Empty sections are left out.
function sections(tabs, byState) {
    var out = [], i, s;
    if (byState) {
        var taken = {};
        for (i = 0; i < STATE_GROUPS.length; i++) {
            var g = STATE_GROUPS[i], rows = [];
            for (var k = 0; k < tabs.length; k++)
                if (g.states.indexOf(tabs[k].state) >= 0) { rows.push(tabs[k]); taken[tabs[k].key] = true; }
            if (rows.length) out.push({ label: g.label, hue: "", rows: rows });
        }
        var idle = tabs.filter(function (t) { return !taken[t.key]; });
        if (idle.length) out.push({ label: IDLE_GROUP, hue: "", rows: idle });
        return out;
    }
    var byName = Object.create(null);     // no prototype: a project named `constructor` or `toString` is just a name
    for (i = 0; i < tabs.length; i++) {
        var name = tabs[i].project || "Terminal";
        s = byName[name];
        if (!s) { s = byName[name] = { label: name, hue: tabs[i].hue, rows: [] }; out.push(s); }
        s.rows.push(tabs[i]);
    }
    return out;
}

// "<1m", "4m", "2h", "3d": how long a tab has been in its state.
function age(since, nowS) {
    if (!since) return "";
    var s = Math.max(0, nowS - since);
    if (s < 45) return "<1m";
    var m = Math.round(s / 60);
    if (m < 60) return m + "m";
    var h = Math.floor(m / 60);
    if (h < 48) return h + "h";
    return Math.floor(h / 24) + "d";
}

var AGENT_NAMES = { claude: "Claude Code", codex: "Codex", gemini: "Gemini", opencode: "OpenCode", cursor: "Cursor", "cursor-agent": "Cursor",
                    agy: "Antigravity", droid: "Droid", amp: "Amp", goose: "Goose", aider: "Aider", crush: "Crush", kimi: "Kimi", qwen: "Qwen" };

function agentName(a) {
    if (!a) return "";
    return AGENT_NAMES[a] || (a.charAt(0).toUpperCase() + a.slice(1));
}

// The row's two lines. Identity first: the title, else the project, else the folder. Then state, in words.
function title(t) {
    return t.title || t.project || t.cwd || "Terminal";
}

function stateWord(t) {
    if (t.state === "waiting") return "Needs you";
    if (t.state === "limited") return "Limited";
    if (t.state === "error") return "Error";
    if (t.state === "working") return "Working";
    if (t.state === "done") return "Finished";
    if (t.state === "idle") return "Idle";
    return "";
}

// The second line, after the state word: what it asks, how far along, when a limit lifts, or where it runs.
function detail(t, nowS) {
    if (t.state === "waiting" && t.question) return t.question;
    if (t.state === "limited" && t.limitReset) {
        var left = t.limitReset - nowS;
        return left > 0 ? "resets in " + age(nowS - left, nowS).replace("<1m", "1m") : "resetting";
    }
    var bits = [];
    if (t.agent && !t.state) bits.push(agentName(t.agent));
    if (t.state === "" || t.state === "idle") {
        if (t.branch) bits.push(t.branch);
        else if (t.cwd) bits.push(t.cwd);
    }
    return bits.join(" · ");
}

// The percent a working tab shows, or -1 (OSC 9;4 reported no amount).
function percent(t) {
    return t.state === "working" && t.progress !== null ? Math.round(t.progress * 100) : -1;
}

// The header: identity of where you are (the focused tab's project, branch), then what needs you.
function header(tabs) {
    var here = null, need = 0, working = 0;
    for (var i = 0; i < tabs.length; i++) {
        if (tabs[i].active) here = tabs[i];
        if (asks(tabs[i])) need++;
        if (tabs[i].state === "working") working++;
    }
    return {
        title: here ? (here.project || title(here)) : "kittymux",
        subtitle: here ? [here.branch, tabs.length + (tabs.length === 1 ? " tab" : " tabs")].filter(function (x) { return x; }).join(" · ")
                       : (tabs.length ? tabs.length + " tabs" : "No kitty running"),
        needsYou: need, working: working
    };
}

// Keyboard: the next row index from `i` by `delta`, clamped (no wrap: the list has ends, like the panel).
function step(i, delta, n) {
    if (n <= 0) return -1;
    if (i < 0) return delta > 0 ? 0 : n - 1;
    return Math.max(0, Math.min(n - 1, i + delta));
}

// The `kittymux` command lines the client runs (never a shell string).
function jumpArgs(bin, t) {
    return t && t.action ? [bin, "act", JSON.stringify(t.action)] : [];
}
// `muted`: what the row shows now (a click not yet confirmed by the scanner counts), so a second click undoes the first.
function muteArgs(bin, t, muted) {
    if (!t || typeof t.agentWindow !== "number") return [];
    var now = muted === undefined ? !!t.muted : !!muted;
    return [bin, now ? "unmute" : "mute", "--pid", String(t.kittyPid), "--window", String(t.agentWindow)];
}

// ── Attach mode: the client drawn over kitty's own vertical bar (Hyprland) ─────────────────────────────────────────────────────────
// kitty knows where its bar is (tabs.json `geometry`, framebuffer pixels); Hyprland knows where the window is (`hyprctl -j clients`,
// logical pixels) and on which monitor (`hyprctl -j monitors`). The overlay is a transparent layer surface laid exactly over the bar,
// minus kitty's divider columns, so kitty's own background, blur and divider stay kitty's and only the content is ours.

var DIVIDER_CELLS = 2;          // tab_bar.SEP_COLS: the divider takes the bar's last two columns (its first two on the right edge)

// The Hyprland window that is this kitty OS window: same pid, mapped; with several, the one whose title and size match.
function matchClient(win, clients) {
    var g = win && win.geometry;
    var own = (clients || []).filter(function (c) { return c && c.pid === win.kitty_pid && c.mapped !== false && !c.hidden; });
    if (own.length <= 1) return own[0] || null;
    var score = function (c) {
        var s = 0;
        if (win.title && c.title === win.title) s += 2;
        if (g && c.size && Math.abs(c.size[0] - g.width) <= 2 && Math.abs(c.size[1] - g.height) <= 2) s += 1;
        return s;
    };
    own.sort(function (a, b) { return score(b) - score(a); });
    return own[0];
}

function overlaps(a, b) {
    return a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
}

// Where the overlay goes, or why it does not show. {visible, monitor, x, y, w, h (logical, relative to the monitor), address} or
// {visible: false, reason}. It hides whenever kitty's bar is not what you see: another workspace, a fullscreen window over it,
// a floating window across the bar, a horizontal bar, no bar.
function placement(win, clients, monitors) {
    var g = win && win.geometry;
    if (!g || !g.bar || (g.edge !== "left" && g.edge !== "right")) return { visible: false, reason: "no vertical bar" };
    var c = matchClient(win, clients);
    if (!c || !c.at || !c.size) return { visible: false, reason: "window not found" };
    var mon = (monitors || []).filter(function (m) { return m.id === c.monitor; })[0];
    if (!mon) return { visible: false, reason: "monitor not found" };
    var ws = c.workspace || {};
    var shown = (mon.activeWorkspace && mon.activeWorkspace.id === ws.id) || (mon.specialWorkspace && mon.specialWorkspace.id === ws.id && ws.id !== undefined);
    if (!shown) return { visible: false, reason: "another workspace" };
    var scale = g.scale > 0 ? g.scale : 1;
    var cell = g.cell ? g.cell[0] : 0;
    var div = DIVIDER_CELLS * cell;
    var bl = g.bar[0], bt = g.bar[1], br = g.bar[2], bb = g.bar[3];
    if (g.edge === "left") br = Math.max(bl + cell, br - div); else bl = Math.min(br - cell, bl + div);
    var rect = {
        x: c.at[0] + bl / scale, y: c.at[1] + bt / scale,
        w: (br - bl) / scale, h: Math.min((bb - bt) / scale, c.size[1] - bt / scale)
    };
    for (var i = 0; i < (clients || []).length; i++) {
        var o = clients[i];
        if (!o || o === c || o.address === c.address || !o.workspace || o.workspace.id !== ws.id || o.hidden || o.mapped === false) continue;
        if (o.fullscreen && !c.fullscreen) return { visible: false, reason: "fullscreen window" };
        // a floating window above kitty and across the bar; kitty floating and focused is the one on top
        var kittyOnTop = c.floating && c.focusHistoryID === 0;
        if (o.floating && !kittyOnTop && o.at && o.size && overlaps(rect, { x: o.at[0], y: o.at[1], w: o.size[0], h: o.size[1] }))
            return { visible: false, reason: "a floating window covers the bar" };
    }
    // Hyprland's monitor x/y are logical; its width/height are the mode in physical pixels.
    var mscale = mon.scale > 0 ? mon.scale : 1;
    return {
        visible: true, monitor: mon.name, address: c.address,
        x: Math.round(rect.x - mon.x), y: Math.round(rect.y - mon.y), w: Math.round(rect.w), h: Math.round(rect.h),
        monitorW: Math.round(mon.width / mscale), monitorH: Math.round(mon.height / mscale)
    };
}

// Hyprland events after which windows move (and animate): the overlay fades out at once and comes back where the window settles.
var MOVING_EVENTS = ["workspace", "workspacev2", "focusedmon", "focusedmonv2", "movewindow", "movewindowv2", "openwindow", "closewindow",
                     "changefloatingmode", "fullscreen", "moveworkspace", "moveworkspacev2", "activespecial", "activespecialv2",
                     "minimized", "togglegroup", "moveintogroup", "moveoutofgroup", "monitoradded", "monitorremoved", "configreloaded"];

function eventMoves(line) {
    var name = String(line || "").split(">>")[0];
    return MOVING_EVENTS.indexOf(name) >= 0;
}
