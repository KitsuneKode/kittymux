// The client's sidebar: a two-line header (where you are, then what needs you), the tabs grouped by space or by state (`g`), one
// gliding highlight, and an inline right-click menu. Rows are kept in a ListModel synced by key, so a tab that changes state updates
// in place, a new one fades in, a closed one fades out, and the rest glide to their new places (one reflow, 200 ms) instead of the
// whole list being rebuilt.
import QtQuick
import qs.config
import qs.services
import "../lib/logic.js" as Logic

FocusScope {
    id: root

    property int selected: -1           // a row index into `model` (keyboard), -1 when none
    readonly property bool keyboard: activeFocus && selected >= 0

    ListModel { id: model }

    // Flatten sections into one list of items with stable keys, then sync the model to it: move, insert, update, remove.
    function rebuild() {
        const want = [];
        for (const s of Feed.sections) {
            want.push({ key: "s:" + s.label, kind: "section", json: JSON.stringify({ label: s.label, hue: s.hue, count: s.rows.length }) });
            for (const t of s.rows) want.push({ key: "t:" + t.key, kind: "tab", json: JSON.stringify(t) });
        }
        for (let i = 0; i < want.length; i++) {
            let j = -1;
            for (let k = i; k < model.count; k++) if (model.get(k).key === want[i].key) { j = k; break; }
            if (j < 0) model.insert(i, want[i]);
            else {
                if (j !== i) model.move(j, i, 1);
                if (model.get(i).json !== want[i].json) model.setProperty(i, "json", want[i].json);
            }
        }
        while (model.count > want.length) model.remove(model.count - 1);
        if (selected >= model.count) selected = model.count - 1;
        if (want.length) settledIn.start();
    }
    // The first fill is not a change: the list appears whole, and only later arrivals and departures animate.
    property bool ready: false
    Timer { id: settledIn; interval: 1; onTriggered: root.ready = true }
    Connections { target: Feed; function onSectionsChanged() { root.rebuild(); } }
    Component.onCompleted: rebuild()

    function rowIndices() { const out = []; for (let i = 0; i < model.count; i++) if (model.get(i).kind === "tab") out.push(i); return out; }
    function move(delta) {
        const rows = rowIndices();
        const at = rows.indexOf(selected);
        const n = Logic.step(at, delta, rows.length);
        selected = n >= 0 ? rows[n] : -1;
        if (selected >= 0) list.positionViewAtIndex(selected, ListView.Contain);
    }
    function selectedTab() { return selected >= 0 && selected < model.count && model.get(selected).kind === "tab" ? JSON.parse(model.get(selected).json) : null; }

    Keys.onPressed: e => {
        if (menu.open) { if (e.key === Qt.Key_Escape) { menu.close(); e.accepted = true; } return; }
        const t = selectedTab();
        if (e.key === Qt.Key_Down || e.key === Qt.Key_J) move(1);
        else if (e.key === Qt.Key_Up || e.key === Qt.Key_K) move(-1);
        else if (e.key === Qt.Key_Home) { selected = -1; move(1); }
        else if (e.key === Qt.Key_End) { selected = -1; move(-1); }
        else if ((e.key === Qt.Key_Return || e.key === Qt.Key_Enter) && t) Feed.jump(t);
        else if (e.key === Qt.Key_G) Feed.toggleGroup();
        else if (e.key === Qt.Key_M && t) Feed.toggleMute(t);
        else if (e.key === Qt.Key_Escape) selected = -1;
        else return;
        e.accepted = true;
    }

    Glass { anchors.fill: parent }

    // ── Header: identity first, then state ───────────────────────────────
    Item {
        id: head
        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
        height: 58
        Column {
            anchors.left: parent.left; anchors.leftMargin: Theme.s4
            anchors.right: badge.left; anchors.rightMargin: Theme.s2
            anchors.verticalCenter: parent.verticalCenter
            spacing: 2
            Label { width: parent.width; text: Feed.header.title; size: Theme.tTitle; weight: Theme.wSemibold }
            Label { width: parent.width; text: Feed.header.subtitle; size: Theme.tCaption; color: Theme.text3 }
        }
        // What needs you: an orange count, present only when something asks.
        Row {
            id: badge
            anchors.right: parent.right; anchors.rightMargin: Theme.s4
            anchors.verticalCenter: parent.verticalCenter
            spacing: 5
            opacity: Feed.header.needsYou > 0 ? 1 : 0
            visible: opacity > 0.001
            Behavior on opacity { NumberAnimation { duration: Theme.enterMs; easing.type: Easing.OutCubic } }
            Rectangle { width: 7; height: 7; radius: 3.5; color: Theme.waiting; anchors.verticalCenter: parent.verticalCenter }
            RollingNumber { value: Feed.header.needsYou; color: Theme.waiting; weight: Theme.wSemibold; anchors.verticalCenter: parent.verticalCenter }
        }
        Rectangle { anchors.bottom: parent.bottom; x: Theme.s4; width: parent.width - Theme.s4 * 2; height: 1; color: Theme.hairline }
    }

    // ── The list ─────────────────────────────────────────────────────────
    ListView {
        id: list
        anchors.top: head.bottom; anchors.bottom: foot.top
        anchors.left: parent.left; anchors.right: parent.right
        anchors.leftMargin: Theme.s1 + 2; anchors.rightMargin: Theme.s1 + 2
        clip: true
        model: model
        boundsBehavior: Flickable.StopAtBounds
        reuseItems: false
        cacheBuffer: 400

        Highlight {
            id: glide
            parent: list.contentItem
            ring: root.keyboard && !hoverTarget
            property Item hoverTarget: null
            target: hoverTarget || (root.keyboard ? list.itemAtIndex(root.selected) : null)
        }

        delegate: Item {
            id: cell
            required property int index
            required property string kind
            required property string json
            readonly property var d: JSON.parse(json)
            width: list.width
            height: kind === "section" ? Theme.sectionH + (index === 0 ? 0 : 6) : Theme.rowH

            SectionHeader {
                visible: cell.kind === "section"
                anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
                label: cell.d.label || ""; hue: cell.d.hue || ""; count: cell.d.count || 0
            }
            TabRow {
                visible: cell.kind === "tab"
                anchors.fill: parent
                tab: cell.kind === "tab" ? cell.d : ({})
                onHoveredChanged: {
                    if (hovered) glide.hoverTarget = cell;
                    else if (glide.hoverTarget === cell) glide.hoverTarget = null;
                }
                onActivated: { root.selected = cell.index; Feed.jump(cell.d); }
                onContextRequested: { root.selected = cell.index; root.forceActiveFocus(); menu.atY = cell.mapToItem(root, 0, cell.height).y; menu.tab = cell.d; }
            }
        }

        // Choreography: arrivals fade up 6 px, departures fade a tier quicker, and the rows around them glide once to their new places.
        add: root.ready ? addTrans : null
        property Transition addT: Transition {
            id: addTrans
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.enterMs; easing.type: Easing.OutCubic }
            NumberAnimation { property: "y"; from: addTrans.ViewTransition.destination.y + 6; duration: Theme.reduceMotion ? 0 : Theme.enterMs; easing.type: Easing.OutCubic }
        }
        remove: root.ready ? removeTrans : null
        property Transition removeT: Transition { id: removeTrans; NumberAnimation { property: "opacity"; to: 0; duration: Theme.exitMs; easing.type: Easing.OutCubic } }
        displaced: root.ready ? displacedTrans : null
        property Transition displacedT: Transition {
            id: displacedTrans
            NumberAnimation { property: "y"; duration: Theme.reduceMotion ? 0 : 200; easing.type: Easing.OutCubic }
            NumberAnimation { property: "opacity"; to: 1; duration: Theme.enterMs }
        }
        move: root.ready ? moveTrans : null
        property Transition moveT: Transition { id: moveTrans; NumberAnimation { property: "y"; duration: Theme.reduceMotion ? 0 : 200; easing.type: Easing.OutCubic } }

        // Nothing to show: say why, quietly.
        Column {
            anchors.centerIn: parent
            visible: model.count === 0 && Feed.loaded
            spacing: 4
            Label { anchors.horizontalCenter: parent.horizontalCenter; text: "No kitty running"; color: Theme.text2; weight: Theme.wMedium }
            Label { anchors.horizontalCenter: parent.horizontalCenter; text: "Tabs appear here as kitty opens them"; size: Theme.tCaption; color: Theme.text3 }
        }
    }

    // ── Footer: the keys, while the keyboard is here ─────────────────────
    Item {
        id: foot
        anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom
        height: 34
        Rectangle { anchors.top: parent.top; x: Theme.s4; width: parent.width - Theme.s4 * 2; height: 1; color: Theme.hairline }
        Label {
            anchors.left: parent.left; anchors.leftMargin: Theme.s4
            anchors.right: parent.right; anchors.rightMargin: Theme.s4
            anchors.verticalCenter: parent.verticalCenter
            text: root.activeFocus ? "↑↓ move   ↵ jump   g group   m mute"
                                   : (Feed.byState ? "By state" : "By space") + "  ·  g to change"
            size: Theme.tMicro; color: Theme.text3
        }
    }

    RowMenu { id: menu; onClosed: root.forceActiveFocus() }
}
