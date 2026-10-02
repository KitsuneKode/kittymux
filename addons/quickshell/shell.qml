// kittymux inbox panel for Quickshell — SAMPLE, UNTESTED (see README.md). Written against docs/inbox.md; adapt to your Quickshell version.
import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Io

ShellRoot {
    id: root

    readonly property string stateDir: Quickshell.env("KITTYMUX_STATE") || ((Quickshell.env("XDG_STATE_HOME") || (Quickshell.env("HOME") + "/.local/state")) + "/kittymux")
    property var inbox: ({ version: 1, unread: 0, needs_you: 0, events: [] })

    FileView {
        id: snapshot
        path: root.stateDir + "/inbox-snapshot.json"
        watchChanges: true
        onFileChanged: reload()
        onLoaded: {
            try { root.inbox = JSON.parse(text()); } catch (e) { /* a half-written file never happens (atomic replace), but never crash the shell */ }
        }
    }

    Process { id: runner }
    function kittymux(args) { runner.command = ["kittymux"].concat(args); runner.running = true; }

    function glyph(e) { return e.severity === "needs-you" ? "!" : e.severity === "warn" ? "⊘" : "·"; }
    function countdown(e) {
        if (e.kind !== "limit" || !e.reset_at) return "";
        var s = Math.max(0, e.reset_at - Date.now() / 1000);
        return " — resets in " + Math.floor(s / 3600) + "h " + Math.floor((s % 3600) / 60) + "m";
    }

    PanelWindow {
        anchors { top: true; right: true }
        margins { top: 8; right: 8 }
        implicitWidth: 420
        implicitHeight: Math.min(480, 44 + list.contentHeight)
        color: "transparent"
        visible: root.inbox.unread > 0

        Rectangle {
            anchors.fill: parent
            radius: 10
            color: "#1e1e2e"
            border.color: root.inbox.needs_you > 0 ? "#f38ba8" : "#45475a"

            Text {
                id: head
                x: 12; y: 10
                color: "#cdd6f4"
                font.pixelSize: 14
                text: "kittymux  " + root.inbox.unread + " unread" + (root.inbox.needs_you > 0 ? "  (" + root.inbox.needs_you + " need you)" : "")
            }

            ListView {
                id: list
                anchors { top: head.bottom; left: parent.left; right: parent.right; bottom: parent.bottom; margins: 10 }
                clip: true
                spacing: 6
                model: root.inbox.events.filter(function (e) { return e.status === "unread"; })
                delegate: Rectangle {
                    width: list.width
                    height: 46
                    radius: 6
                    color: mouse.containsMouse ? "#313244" : "transparent"
                    Text {
                        anchors { left: parent.left; leftMargin: 8; verticalCenter: parent.verticalCenter }
                        width: parent.width - 40
                        elide: Text.ElideRight
                        color: modelData.severity === "needs-you" ? "#f9e2af" : "#cdd6f4"
                        font.pixelSize: 13
                        text: root.glyph(modelData) + "  " + modelData.agent + " · " + modelData.kind + " · " + modelData.tab + "\n" + (modelData.body || modelData.title) + root.countdown(modelData)
                    }
                    MouseArea {
                        id: mouse
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: root.kittymux(["inbox", "jump", modelData.id])
                    }
                    Text {
                        anchors { right: parent.right; rightMargin: 8; verticalCenter: parent.verticalCenter }
                        color: "#6c7086"
                        text: "×"
                        MouseArea { anchors.fill: parent; onClicked: root.kittymux(["inbox", "ack", modelData.id]) }
                    }
                }
            }
        }
    }
}
