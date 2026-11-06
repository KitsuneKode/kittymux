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
                key: w.kitty_pid + "." + t.tab_id,
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
    var byName = {};
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
function muteArgs(bin, t) {
    if (!t || typeof t.agentWindow !== "number") return [];
    return [bin, t.muted ? "unmute" : "mute", "--pid", String(t.kittyPid), "--window", String(t.agentWindow)];
}
