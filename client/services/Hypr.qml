// Hyprland, for attach mode: where every window and monitor is (`hyprctl -j clients`, `hyprctl -j monitors`), asked again when Hyprland
// says something changed (its event socket, read line by line; no poll) and when kitty republishes tabs.json (a resize has no Hyprland
// event). Events that move windows set `moving` until things settle, so an overlay fades out while Hyprland animates and comes back
// where the window lands, instead of trailing it.
pragma Singleton

import QtQuick
import Quickshell
import Quickshell.Io
import "../lib/logic.js" as Logic

Singleton {
    id: root

    readonly property string signature: Quickshell.env("HYPRLAND_INSTANCE_SIGNATURE") || ""
    readonly property string runtime: Quickshell.env("XDG_RUNTIME_DIR") || ""
    readonly property bool available: signature !== "" && runtime !== ""
    property var clients: []
    property var monitors: []
    property bool moving: false
    property int settleMs: 420                    // Hyprland's window and workspace springs settle within this

    function refresh() {
        if (!available) return;
        if (clientsProc.running || monitorsProc.running) { again = true; return; }
        clientsProc.running = true;
        monitorsProc.running = true;
    }
    property bool again: false

    Process {
        id: clientsProc
        command: ["hyprctl", "-j", "clients"]
        stdout: StdioCollector {
            onStreamFinished: { try { root.clients = JSON.parse(text); } catch (e) {} if (root.again) { root.again = false; Qt.callLater(root.refresh); } }
        }
    }
    Process {
        id: monitorsProc
        command: ["hyprctl", "-j", "monitors"]
        stdout: StdioCollector { onStreamFinished: { try { root.monitors = JSON.parse(text); } catch (e) {} } }
    }

    Socket {
        id: events
        path: root.available ? root.runtime + "/hypr/" + root.signature + "/.socket2.sock" : ""
        connected: root.available
        parser: SplitParser {
            onRead: line => {
                if (Logic.eventMoves(line)) { root.moving = true; settle.restart(); }
                else nudge.restart();
            }
        }
    }
    // A burst of events is one refresh.
    Timer { id: nudge; interval: 40; onTriggered: root.refresh() }
    Timer { id: settle; interval: root.settleMs; onTriggered: { root.refresh(); root.moving = false; } }

    Component.onCompleted: refresh()
}
