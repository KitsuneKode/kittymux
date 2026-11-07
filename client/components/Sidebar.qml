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
    property int activeIndex: -1        // the row of the tab you are in
    readonly property bool keyboard: activeFocus && selected >= 0
    // Attach mode: this sidebar is one kitty window's own bar (its tabs only, no surface of its own: kitty's background shows through).
    property string windowKey: ""
    property bool attached: false
    // Attached, "where you are" is this window's active tab, focused or not: it is what kitty's own bar marked.
    readonly property var tabs: windowKey ? Feed.tabs.filter(t => t.windowKey === windowKey).map(t => Object.assign({}, t, { active: t.activeInWindow }))
                                          : Feed.tabs
    readonly property var sections: Logic.sections(tabs, Feed.byState)
    readonly property var header: Logic.header(tabs)

    ListModel { id: model }

    // Flatten sections into one list of items with stable keys, then sync the model to it: move, insert, update, remove.
    function rebuild() {
        const want = [];
        for (const s of root.sections) {
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
        activeIndex = want.findIndex(w => w.kind === "tab" && JSON.parse(w.json).active);
        Qt.callLater(here.pick);
        if (selected >= model.count) selected = model.count - 1;
        if (want.length) settledIn.start();
    }
    // The first fill is not a change: the list appears whole, and only later arrivals and departures animate.
    property bool ready: false
    Timer { id: settledIn; interval: 1; onTriggered: root.ready = true }
    onSectionsChanged: rebuild()
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

    Glass { anchors.fill: parent; visible: !root.attached }

    // ── Header: identity first, then state ───────────────────────────────
    Item {
        id: head
        anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
        // Attached, the window's rounded corner cuts the first line. The inset is the corner, not a new margin system.
        anchors.topMargin: root.attached ? 18 : 0
        height: root.attached ? 72 : 58
        Column {
            anchors.left: parent.left; anchors.leftMargin: Theme.edge
            anchors.right: badge.left; anchors.rightMargin: Theme.s2
            anchors.verticalCenter: parent.verticalCenter
            spacing: 2
            Label { width: parent.width; text: root.header.title; size: Theme.tTitle; weight: Theme.wSemibold }
            Label { width: parent.width; text: root.header.subtitle; size: Theme.tCaption; color: Theme.text3 }
        }
        // What needs you: an orange count, present only when something asks.
        Row {
            id: badge
            anchors.right: parent.right; anchors.rightMargin: Theme.edge
            anchors.verticalCenter: parent.verticalCenter
            spacing: 5
            opacity: root.header.needsYou > 0 ? 1 : 0
            visible: opacity > 0.001
            Behavior on opacity { NumberAnimation { duration: Theme.enterMs; easing.type: Easing.OutCubic } }
            Rectangle { width: 7; height: 7; radius: 3.5; color: Theme.waiting; anchors.verticalCenter: parent.verticalCenter }
            RollingNumber { value: root.header.needsYou; color: Theme.waiting; weight: Theme.wSemibold; anchors.verticalCenter: parent.verticalCenter }
        }
        Rectangle { anchors.bottom: parent.bottom; x: Theme.edge; width: parent.width - Theme.edge * 2; height: 1; color: Theme.hairline }
    }

    // ── The list ─────────────────────────────────────────────────────────
    ListView {
        id: list
        anchors.top: head.bottom; anchors.bottom: foot.top
        anchors.left: parent.left; anchors.right: parent.right
        anchors.leftMargin: Theme.listInset; anchors.rightMargin: Theme.listInset
        clip: true
        model: model
        boundsBehavior: Flickable.StopAtBounds
        reuseItems: false
        cacheBuffer: 400
        onContentHeightChanged: here.pick()

        // Where you are: ONE accent mark (at 45%: state colours lead) that glides to the tab you switch to on the moderate spring, so
        // the eye follows the move instead of one row's mark fading out while another fades in.
        Rectangle {
            id: here
            parent: list.contentItem
            property Item row: null
            property bool placed: false
            // itemAtIndex is not a binding that updates when delegates are created: look again whenever the list changes shape.
            function pick() { row = root.activeIndex >= 0 ? list.itemAtIndex(root.activeIndex) : null; follow(); }
            x: 1; width: 3; height: 18; radius: 1.5
            y: hereY.value
            z: 60
            color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, Theme.accentHairline)
            opacity: row ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: Theme.enterMs; easing.type: Easing.OutCubic } }
            Spring { id: hereY; tier: Theme.springModerate; epsilon: 0.25 }
            function follow() {
                if (!row) return;
                const t = row.y + (row.height - height) / 2;
                if (!placed || !root.ready) { hereY.snap(t); placed = true; } else hereY.target = t;
            }
            onRowChanged: follow()
            Connections { target: here.row; function onYChanged() { here.follow(); } }
        }

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
        Rectangle { anchors.top: parent.top; x: Theme.edge; width: parent.width - Theme.edge * 2; height: 1; color: Theme.hairline }
        Label {
            anchors.left: parent.left; anchors.leftMargin: Theme.edge
            anchors.right: parent.right; anchors.rightMargin: Theme.edge
            anchors.verticalCenter: parent.verticalCenter
            text: root.activeFocus ? "↑↓ move   ↵ jump   g group   m mute"
                                   : (Feed.byState ? "By state" : "By space") + "  ·  g to change"
            size: Theme.tMicro; color: Theme.text2
        }
    }

    RowMenu { id: menu; onClosed: root.forceActiveFocus() }
}
