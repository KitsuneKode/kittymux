// kittymux client: kitty stays the terminal; this draws the UI beside it on the GPU (Qt Quick), from kittymux's published files.
//   kittymux client [start|stop|toggle]       (bin/kittymux runs `qs -p <this dir>` with KITTYMUX_BIN / KITTYMUX_ICONS set)
// Wayland: a layer-shell panel on the screen's edge (namespace `kittymux-client`, for the compositor's blur rule), keyboard on demand
// (click it to type into it; it never takes the keyboard by itself). KITTYMUX_CLIENT_FLOAT=1: an ordinary window instead (X11, rigs).
//   KITTYMUX_CLIENT_EDGE=left|right (default left)   KITTYMUX_CLIENT_WIDTH=<px> (default 300)
import QtQuick
import Quickshell
import Quickshell.Wayland
import qs.config
import qs.services
import qs.components

ShellRoot {
    id: shell
    readonly property bool floating: Quickshell.env("KITTYMUX_CLIENT_FLOAT") === "1"
    readonly property bool right: Quickshell.env("KITTYMUX_CLIENT_EDGE") === "right"
    readonly property int panelWidth: Math.max(220, Math.min(520, Number(Quickshell.env("KITTYMUX_CLIENT_WIDTH") || 300) || 300))
    readonly property int gap: 8

    Loader {
        active: !shell.floating
        sourceComponent: PanelWindow {
            anchors { left: !shell.right; right: shell.right; top: true; bottom: true }
            implicitWidth: shell.panelWidth + shell.gap
            exclusiveZone: shell.panelWidth + shell.gap
            color: "transparent"
            WlrLayershell.namespace: "kittymux-client"
            WlrLayershell.layer: WlrLayer.Top
            WlrLayershell.keyboardFocus: WlrKeyboardFocus.OnDemand
            Sidebar {
                anchors.fill: parent
                anchors.topMargin: shell.gap; anchors.bottomMargin: shell.gap
                anchors.leftMargin: shell.right ? 0 : shell.gap; anchors.rightMargin: shell.right ? shell.gap : 0
                focus: true
            }
        }
    }
    Loader {
        active: shell.floating
        sourceComponent: FloatingWindow {
            implicitWidth: shell.panelWidth + shell.gap * 2
            implicitHeight: Number(Quickshell.env("KITTYMUX_CLIENT_HEIGHT") || 640) || 640
            color: Quickshell.env("KITTYMUX_CLIENT_BACKDROP") || "#202028"
            title: "kittymux client"
            Sidebar { anchors.fill: parent; anchors.margins: shell.gap; focus: true }
        }
    }
}
