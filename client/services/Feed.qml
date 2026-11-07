// The kittymux client's one source of truth: tabs.json (docs/inbox.md), watched, never polled. The scanner rewrites it only when
// something a client draws changed, so at rest nothing here wakes. The group choice (`g`) is the panel's own file, so the panel and
// the client agree. Actions go through the `kittymux` CLI with argument lists (never a shell string), on the kitty the row names.
pragma Singleton

import QtQuick
import Quickshell
import Quickshell.Io
import qs.config
import "../lib/logic.js" as Logic

Singleton {
    id: root

    readonly property string home: Quickshell.env("HOME")
    readonly property string stateDir: Quickshell.env("KITTYMUX_STATE")
        || ((Quickshell.env("XDG_STATE_HOME") || home + "/.local/state") + "/kittymux")
    readonly property string bin: Quickshell.env("KITTYMUX_BIN") || "kittymux"
    readonly property string iconDir: Quickshell.env("KITTYMUX_ICONS") || ""

    property var doc: null
    property var alive: ({})                       // kitty pid → false once it has exited (tabs.json keeps it until another kitty prunes)
    readonly property var tabs: Logic.tabsOf(doc, alive)
    property bool byState: false
    readonly property var sections: Logic.sections(tabs, byState)
    readonly property var header: Logic.header(tabs)
    readonly property bool loaded: doc !== null
    // The OS windows of running kitties (attach mode draws one overlay per window with a vertical bar).
    readonly property var windows: ((doc && doc.windows) || []).filter(w => w && alive[w.kitty_pid] !== false)
    // Muted on click, before the scanner's next pass confirms it: the bell-slash answers at once.
    property var pendingMute: ({})

    // The palette of the focused kitty (else the first): every colour token follows it.
    onDocChanged: {
        const ws = (doc && doc.windows) || [];
        const w = ws.find(x => x.focused) || ws[0];
        if (w && w.palette) Theme.palette = w.palette;
        pendingMute = ({});
        checkAlive();
    }

    FileView {
        id: tabsFile
        path: root.stateDir + "/tabs.json"
        watchChanges: true
        printErrors: false
        onFileChanged: reload()
        onLoaded: {
            try { root.doc = JSON.parse(text()); } catch (e) { /* a half-written file cannot happen (atomic rename); keep the last one */ }
        }
        onLoadFailed: root.doc = ({ version: 1, windows: [] })
    }

    FileView {
        id: groupFile
        path: root.stateDir + "/panel-group"
        watchChanges: true
        printErrors: false
        onFileChanged: reload()
        onLoaded: root.byState = text().trim() === "state"
        onLoadFailed: root.byState = false
    }

    // kittymux's `motion` switch (kittymux features): its off file stops the working ring's steps, as it stops the bar's.
    property bool motion: true
    FileView {
        id: motionOff
        path: root.stateDir + "/motion-off"
        printErrors: false
        onLoaded: root.motion = false
        onLoadFailed: root.motion = true
    }
    onTabsChanged: motionOff.reload()

    function toggleGroup() {
        byState = !byState;
        groupFile.setText(byState ? "state\n" : "");
    }

    // Attach mode: tell each kitty that this client draws its bar (kittymux_layout.attach), so its own bar draws no tabs. The record
    // names this process; if the client dies, the record is dead with it and the bar draws itself again.
    property int ownPid: 0
    Process {
        id: whoami
        command: ["sh", "-c", "echo $PPID"]
        running: true
        stdout: StdioCollector { onStreamFinished: root.ownPid = Number(text.trim()) || 0 }
    }
    property var attachedTo: ({})
    function setAttached(kittyPid, on) {
        if (!ownPid || !kittyPid || !!attachedTo[kittyPid] === on) return;
        const a = Object.assign({}, attachedTo);
        a[kittyPid] = on;
        attachedTo = a;
        Quickshell.execDetached([bin, "client", on ? "attach" : "detach", String(kittyPid), String(ownPid)]);
    }

    function jump(t) {
        const args = Logic.jumpArgs(bin, t);
        if (args.length) Quickshell.execDetached(args);
    }

    function toggleMute(t) {
        const args = Logic.muteArgs(bin, t);
        if (!args.length) return;
        const p = Object.assign({}, pendingMute);
        p[t.key] = !t.muted;
        pendingMute = p;
        Quickshell.execDetached(args);
    }

    function mutedOf(t) { return !!(t && (t.key in pendingMute ? pendingMute[t.key] : t.muted)); }

    // Which listed kitties still run. Asked when the document changes and every 20 s while something is listed: a kitty that exited
    // last leaves its rows behind (nobody else is left to prune them), and the client must not show tabs that are gone.
    function checkAlive() {
        const pids = [...new Set(((doc && doc.windows) || []).map(w => w.kitty_pid).filter(p => typeof p === "number"))];
        if (!pids.length || probe.running) return;
        probe.command = ["sh", "-c", 'for p; do [ -d "/proc/$p" ] && echo "$p"; done; echo .', "sh", ...pids.map(String)];
        probe.asked = pids;
        probe.running = true;
    }
    Process {
        id: probe
        property var asked: []
        stdout: StdioCollector {
            onStreamFinished: {
                const live = new Set(text.split("\n").filter(x => /^\d+$/.test(x)).map(Number));
                const a = {};
                for (const p of probe.asked) a[p] = live.has(p);
                root.alive = a;
            }
        }
    }
    Timer { interval: 20000; repeat: true; running: root.tabs.length > 0; onTriggered: root.checkAlive() }

    // Ages ("4m") read this; it ticks once a minute and only while a tab has a state with an age.
    property real nowS: Date.now() / 1000
    Timer {
        interval: 30000; repeat: true
        running: root.tabs.some(t => t.state === "done" || t.state === "waiting" || t.state === "limited")
        onTriggered: root.nowS = Date.now() / 1000
    }
}
