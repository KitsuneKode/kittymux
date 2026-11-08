// The right-click menu of a row, inline in the panel (no separate window, nothing takes the screen): Jump, and Mute / Unmute.
// It grows from where it was opened on the moderate spring (0.96 -> 1 and a fade), and leaves a tier quicker. Esc or a click outside closes it.
import QtQuick
import qs.config
import qs.services

Item {
    id: menu
    property var tab: null
    property real atY: 0
    readonly property bool open: tab !== null
    anchors.fill: parent
    visible: card.opacity > 0.001
    z: 100

    signal closed()
    function close() { tab = null; closed(); }

    MouseArea { anchors.fill: parent; enabled: menu.open; acceptedButtons: Qt.AllButtons; onPressed: menu.close() }

    Rectangle {
        id: card
        x: Theme.s4
        y: Math.min(Math.max(Theme.s2, menu.atY), menu.height - height - Theme.s2)
        width: menu.width - Theme.s4 * 2
        height: col.implicitHeight + Theme.s1 * 2
        radius: Theme.r2
        color: Theme.lightTheme ? Theme.bg : Qt.rgba(Theme.bg.r * 0.8 + 0.03, Theme.bg.g * 0.8 + 0.03, Theme.bg.b * 0.8 + 0.035, 1)
        border.width: 1; border.color: Theme.hairline
        transformOrigin: Item.Top
        opacity: menu.open ? 1 : 0
        scale: menu.open || Theme.reduceMotion ? 1 : 0.96
        Behavior on opacity { NumberAnimation { duration: menu.open ? Theme.enterMs : Theme.springModerate.exitMs; easing.type: Easing.OutCubic } }
        Behavior on scale { NumberAnimation { duration: menu.open ? Theme.enterMs : Theme.springModerate.exitMs; easing.type: Easing.OutCubic } }

        Column {
            id: col
            x: Theme.s1; y: Theme.s1
            width: parent.width - Theme.s1 * 2
            Repeater {
                model: menu.tab ? [
                    { id: "jump", label: "Jump to tab", key: "↵" },
                    { id: "mute", label: Feed.mutedOf(menu.tab) ? "Unmute" : "Mute", key: "m", off: typeof menu.tab.agentWindow !== "number" }
                ] : []
                Item {
                    id: entry
                    required property var modelData
                    width: col.width; height: 32
                    opacity: entry.modelData.off ? 0.45 : 1
                    Rectangle { anchors.fill: parent; radius: Theme.r1; color: area.containsMouse && !entry.modelData.off ? Theme.washHi : "transparent"
                                Behavior on color { ColorAnimation { duration: Theme.hoverMs } } }
                    Label { x: Theme.s2 + 2; anchors.verticalCenter: parent.verticalCenter; text: entry.modelData.label; weight: Theme.wMedium }
                    Label { anchors.right: parent.right; anchors.rightMargin: Theme.s2 + 2; anchors.verticalCenter: parent.verticalCenter
                            text: entry.modelData.key; size: Theme.tCaption; color: Theme.text3; elide: Text.ElideNone }
                    MouseArea {
                        id: area; anchors.fill: parent; hoverEnabled: true; enabled: !entry.modelData.off
                        onClicked: {
                            const t = menu.tab;
                            menu.close();
                            if (entry.modelData.id === "jump") Feed.jump(t); else Feed.toggleMute(t);
                        }
                    }
                }
            }
        }
    }
}
