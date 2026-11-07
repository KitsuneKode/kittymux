// One tab, two lines. Identity first (the title, in the text colour, heavier where you are), then state in words, with only the state
// word coloured. The ring around the agent's mark carries the same state at a glance. Where you are is the list's one gliding accent
// mark (Sidebar). Press: 0.985, 140 ms; hover is the list's one gliding highlight.
import QtQuick
import qs.config
import qs.services
import "../lib/logic.js" as Logic

Item {
    id: row

    property var tab: ({})
    property bool selected: false
    readonly property bool muted: Feed.mutedOf(tab)
    readonly property int pct: Logic.percent(tab)
    readonly property string word: Logic.stateWord(tab)
    readonly property string detail: Logic.detail(tab, Feed.nowS)
    readonly property string age: (tab.state === "done" || tab.state === "waiting") ? Logic.age(tab.since, Feed.nowS) : ""
    readonly property color wordColor: Theme.toneColor(Logic.tone(Object.assign({}, tab, { muted: muted })))

    signal activated()
    signal contextRequested()
    property alias hovered: mouse.containsMouse

    implicitHeight: Theme.rowH

    Item {
        id: body
        anchors.fill: parent
        anchors.leftMargin: Theme.s3; anchors.rightMargin: Theme.s3
        scale: mouse.pressed && !Theme.reduceMotion ? Theme.pressScale : 1
        Behavior on scale { NumberAnimation { duration: Theme.pressMs; easing.type: Easing.OutCubic } }

        StateRing {
            id: ring
            width: Theme.mark; height: Theme.mark
            anchors.verticalCenter: parent.verticalCenter
            state: row.tab.state || ""
            progress: row.pct >= 0 ? row.pct / 100 : -1
            muted: row.muted
            Brand {
                anchors.centerIn: parent
                width: 14; height: 14
                brand: row.tab.brand || ""
                agent: row.tab.agent || ""
                color: row.muted ? Theme.text3 : (row.tab.agent ? Theme.text : Theme.text2)
            }
        }

        Column {
            anchors.left: ring.right; anchors.leftMargin: 10
            anchors.right: side.left; anchors.rightMargin: Theme.s2
            anchors.verticalCenter: parent.verticalCenter
            spacing: 1
            Label {
                width: parent.width
                text: Logic.title(row.tab)
                size: Theme.tBody
                // Heavier where you are. The column is fixed-width and elides, so the weight never moves a neighbour.
                weight: row.tab.active ? Theme.wSemibold : Theme.wMedium
                color: row.muted ? Theme.text2 : Theme.text
            }
            Row {
                width: parent.width
                spacing: 0
                Label {
                    id: wordLabel
                    text: row.muted && row.word ? "Muted" : row.word
                    visible: text !== ""
                    size: Theme.tCaption; weight: Theme.wMedium
                    color: row.muted ? Theme.text3 : row.wordColor
                    elide: Text.ElideNone
                    Behavior on color { ColorAnimation { duration: Theme.enterMs } }
                }
                Label {
                    text: (wordLabel.visible && row.detail ? " · " : "") + row.detail
                    visible: row.detail !== ""
                    width: Math.max(0, parent.width - (wordLabel.visible ? wordLabel.implicitWidth : 0))
                    size: Theme.tCaption
                    color: Theme.text3
                }
            }
        }

        Row {
            id: side
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            spacing: 6
            RollingNumber {
                visible: row.pct >= 0
                value: Math.max(0, row.pct); suffix: "%"
                anchors.verticalCenter: parent.verticalCenter
            }
            Label {
                visible: row.pct < 0 && row.age !== ""
                text: row.age
                size: Theme.tCaption; color: Theme.text3; tabular: true; elide: Text.ElideNone
                anchors.verticalCenter: parent.verticalCenter
            }
            Label {
                visible: row.muted
                text: ""
                font.family: Theme.fontGlyph
                size: Theme.tCaption; color: Theme.text3; elide: Text.ElideNone
                anchors.verticalCenter: parent.verticalCenter
            }
            Label {
                visible: (row.tab.panes || 1) > 1
                text: " " + row.tab.panes
                font.family: Theme.fontGlyph
                size: Theme.tMicro; color: Theme.text3; elide: Text.ElideNone
                anchors.verticalCenter: parent.verticalCenter
            }
        }
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        cursorShape: Qt.PointingHandCursor
        onClicked: e => e.button === Qt.RightButton ? row.contextRequested() : row.activated()
    }
}
