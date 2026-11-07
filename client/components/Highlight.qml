// ONE hover highlight per list that glides from row to row on the fast spring instead of every row blinking its own (Fluid
// Functionalism's fluid hover). Leaving into empty space fades it out; the next row lit fades it in fresh where it lands rather than
// sliding over from where it last was. `ring` makes it the keyboard selection (a brighter wash and the accent edge).
import QtQuick
import qs.config

Item {
    id: h

    property Item target: null
    property bool ring: false
    property real radius: Theme.r2

    z: -1
    visible: opacity > 0.001
    opacity: target ? 1 : 0
    Behavior on opacity { NumberAnimation { duration: h.target ? Theme.hoverMs : Theme.springFast.exitMs * 2; easing.type: Easing.OutCubic } }

    x: sx.value; y: sy.value; width: sw.value; height: sh.value
    Spring { id: sx; tier: Theme.springFast; epsilon: 0.25 }
    Spring { id: sy; tier: Theme.springFast; epsilon: 0.25 }
    Spring { id: sw; tier: Theme.springFast; epsilon: 0.25 }
    Spring { id: sh; tier: Theme.springFast; epsilon: 0.25 }

    property bool fresh: true
    onTargetChanged: if (!target) freshTimer.restart(); else { freshTimer.stop(); follow(); }
    Timer { id: freshTimer; interval: 160; onTriggered: h.fresh = true }
    // Rows move (a list reflows, it scrolls): follow the target while one is lit; at rest the springs stop.
    Connections {
        target: h.target
        function onYChanged() { h.follow(); }
        function onHeightChanged() { h.follow(); }
    }

    function follow() {
        if (!target || !parent) return;
        const p = target.mapToItem(parent, 0, 0);
        if (fresh || Theme.reduceMotion) {
            sx.snap(p.x); sy.snap(p.y); sw.snap(target.width); sh.snap(target.height);
            fresh = false;
        } else {
            sx.target = p.x; sy.target = p.y; sw.target = target.width; sh.target = target.height;
        }
    }

    Rectangle {
        anchors.fill: parent
        radius: h.radius
        color: h.ring ? Theme.washHi : Theme.wash
        Behavior on color { ColorAnimation { duration: Theme.hoverMs } }
    }
}
