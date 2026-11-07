// Attach mode: the client laid exactly over ONE kitty window's own vertical bar (Hyprland). kitty keeps the bar's place, background,
// blur and divider and draws no tabs there (kittymux_layout.attach); this transparent layer surface draws the content on top, so the
// sidebar belongs to the window like Rex's does. It shows only while the bar is what you see (Logic.placement: same workspace, nothing
// fullscreen or floating over it) and fades out while Hyprland moves windows, coming back where the window lands.
import QtQuick
import Quickshell
import Quickshell.Wayland
import qs.config
import qs.services
import "../lib/logic.js" as Logic

Scope {
    id: scope
    required property var modelData                 // a tabs.json window
    readonly property var place: Logic.placement(modelData, Hypr.clients, Hypr.monitors)
    readonly property var screenFor: place.visible ? (Quickshell.screens.find(s => s.name === place.monitor) || null) : null
    readonly property bool shown: place.visible && !Hypr.moving && screenFor !== null

    LazyLoader {
        active: scope.screenFor !== null
        PanelWindow {
            screen: scope.screenFor
            anchors { top: true; left: true }
            exclusionMode: ExclusionMode.Ignore
            margins { left: scope.place.x || 0; top: scope.place.y || 0 }
            implicitWidth: Math.max(1, scope.place.w || 1)
            implicitHeight: Math.max(1, scope.place.h || 1)
            color: "transparent"
            WlrLayershell.namespace: "kittymux-client"
            WlrLayershell.layer: WlrLayer.Top
            WlrLayershell.keyboardFocus: WlrKeyboardFocus.OnDemand
            Sidebar {
                anchors.fill: parent
                attached: true
                windowKey: scope.modelData.key
                focus: true
                // Leave the way kitty does: out quickly while windows move, back once they land.
                opacity: scope.shown ? 1 : 0
                Behavior on opacity {
                    NumberAnimation { duration: scope.shown ? Theme.enterMs : Theme.springFast.exitMs; easing.type: Easing.OutCubic }
                }
            }
        }
    }
}
