// The tab's state as a ring around its mark: colour only for state. Working: a quarter arc that steps a quarter turn every 3 s
// (kittymux's calm-motion rule; each step glides, then rests) or, when the program reports an amount, an arc that fills to it on the moderate spring
// and holds still. Needs you / limited: a full orange ring, with one pulse when it arrives (never a loop). Finished: green. Error: red.
// Idle or no agent: no ring. Muted: only the faint track.
import QtQuick
import QtQuick.Shapes
import qs.config
import qs.services

Item {
    id: ring

    property string state: ""
    property real progress: -1          // 0-1, or -1 when unknown
    property bool muted: false
    property real stroke: 2

    readonly property bool turning: state === "working" && progress < 0 && !muted
    readonly property color tone: muted ? Theme.faint
        : (state === "waiting" || state === "limited") ? Theme.waiting
        : state === "error" ? Theme.alert : state === "done" ? Theme.done : Theme.text
    readonly property real sweepTarget: muted ? 0
        : turning ? 90
        : state === "working" ? Math.max(4, progress * 360)
        : (state === "" || state === "idle") ? 0 : 360

    Spring { id: sweep; tier: Theme.springModerate; epsilon: 0.2; target: ring.sweepTarget; Component.onCompleted: settle() }

    // The track: present whenever there is a state, so a filling arc reads against it.
    Shape {
        anchors.fill: parent
        visible: ring.state !== "" && ring.state !== "idle"
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
            strokeColor: Theme.track; strokeWidth: ring.stroke; fillColor: "transparent"
            PathAngleArc { centerX: ring.width / 2; centerY: ring.height / 2; radiusX: ring.width / 2 - ring.stroke / 2; radiusY: radiusX; startAngle: 0; sweepAngle: 360 }
        }
    }
    Item {
        id: arcBox
        anchors.fill: parent
        Shape {
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeColor: ring.tone; strokeWidth: ring.stroke; fillColor: "transparent"; capStyle: ShapePath.RoundCap
                PathAngleArc { centerX: ring.width / 2; centerY: ring.height / 2; radiusX: ring.width / 2 - ring.stroke / 2; radiusY: radiusX; startAngle: -90; sweepAngle: sweep.value }
            }
        }
        // kittymux's calm-motion rule: the working mark steps a quarter turn every 3 s, it never spins. Here each step glides over
        // 0.6 s and then rests, so the ring reads as alive without a frame drawn between steps. `motion` off (kittymux features) or
        // reduced motion: it holds still.
        Behavior on rotation {
            enabled: !Theme.reduceMotion
            NumberAnimation { duration: Theme.stepGlideMs; easing.type: Easing.InOutCubic }
        }
        Timer {
            interval: Theme.stepMs
            repeat: true
            running: ring.turning && Feed.motion && !Theme.reduceMotion && ring.visible
            onTriggered: arcBox.rotation += 90
        }
        // Stopped turning: settle back upright, so a filled ring starts at the top.
        Connections {
            target: ring
            function onTurningChanged() { if (!ring.turning) { arcBox.rotation = 0; } }
        }
    }

    // One cue when the tab starts asking for you.
    property bool asking: (state === "waiting" || state === "limited") && !muted
    onAskingChanged: if (asking && !Theme.reduceMotion) pulse.restart()
    SequentialAnimation {
        id: pulse
        NumberAnimation { target: ring; property: "scale"; to: 1.14; duration: 140; easing.type: Easing.OutCubic }
        NumberAnimation { target: ring; property: "scale"; to: 1.0; duration: 260; easing.type: Easing.OutCubic }
    }
}
