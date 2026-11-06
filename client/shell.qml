// kittymux client: kitty stays the terminal; this draws the UI on the GPU (Qt Quick) from kittymux's published files.
//   kittymux client [start|stop|toggle]       (bin/kittymux runs `qs -p <this dir>` with KITTYMUX_BIN / KITTYMUX_ICONS set)
// Modes (KITTYMUX_CLIENT_MODE):
//   attach (default on Hyprland)  laid over each kitty window's own vertical bar, so the sidebar is part of the window (AttachedBar)
//   dock                          a layer-shell column on the screen's edge (KITTYMUX_CLIENT_EDGE=left|right, KITTYMUX_CLIENT_WIDTH)
// KITTYMUX_CLIENT_FLOAT=1: an ordinary window instead (X11, rigs); with mode attach, sized to the first kitty's bar and painted with
// kitty's bar colour, so a rig can lay it over a real kitty and take the picture.
import QtQuick
import Quickshell
import Quickshell.Wayland
import qs.config
import qs.services
import qs.components

ShellRoot {
    id: shell
    readonly property bool floating: Quickshell.env("KITTYMUX_CLIENT_FLOAT") === "1"
    readonly property string mode: Quickshell.env("KITTYMUX_CLIENT_MODE") || (Hypr.available && !floating ? "attach" : "dock")
    readonly property bool right: Quickshell.env("KITTYMUX_CLIENT_EDGE") === "right"
    readonly property int panelWidth: Math.max(220, Math.min(520, Number(Quickshell.env("KITTYMUX_CLIENT_WIDTH") || 300) || 300))
    readonly property int gap: 8

    // Attach: tell each kitty with a vertical bar that its bar is drawn here (and nothing else is drawn twice).
    readonly property var attachable: Feed.windows.filter(w => w.geometry && (w.geometry.edge === "left" || w.geometry.edge === "right"))
    function syncAttach() {
        if (mode !== "attach") return;
        const pids = new Set(attachable.map(w => w.kitty_pid));
        for (const w of Feed.windows) Feed.setAttached(w.kitty_pid, pids.has(w.kitty_pid));
    }
    onAttachableChanged: syncAttach()
    Connections { target: Feed; function onOwnPidChanged() { shell.syncAttach(); } }

    Variants {
        model: shell.mode === "attach" && !shell.floating ? shell.attachable : []
        AttachedBar {}
    }

    Loader {
        active: shell.mode === "dock" && !shell.floating
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
    // Rigs and X11: an ordinary window. Attach preview: the size of the first kitty's bar (minus kitty's divider), kitty's bar colour.
    readonly property var previewWin: shell.attachable[0] || null
    readonly property var previewGeo: previewWin ? previewWin.geometry : null
    Loader {
        // an attach preview waits for kitty's geometry: a window mapped at a guessed size is not resized without a window manager
        active: shell.floating && (shell.mode !== "attach" || shell.previewGeo !== null)
        sourceComponent: FloatingWindow {
            id: preview
            readonly property bool attach: shell.mode === "attach" && shell.previewGeo !== null
            implicitWidth: attach ? Math.round((shell.previewGeo.bar[2] - shell.previewGeo.bar[0] - 2 * shell.previewGeo.cell[0]) / shell.previewGeo.scale)
                                  : shell.panelWidth + shell.gap * 2
            implicitHeight: attach ? Math.round((shell.previewGeo.bar[3] - shell.previewGeo.bar[1]) / shell.previewGeo.scale)
                                   : (Number(Quickshell.env("KITTYMUX_CLIENT_HEIGHT") || 640) || 640)
            color: attach ? Theme.bar : (Quickshell.env("KITTYMUX_CLIENT_BACKDROP") || "#202028")
            title: "kittymux client"
            Sidebar {
                anchors.fill: parent
                anchors.margins: preview.attach ? 0 : shell.gap
                attached: preview.attach
                windowKey: preview.attach ? shell.previewWin.key : ""
                focus: true
            }
        }
    }
}
