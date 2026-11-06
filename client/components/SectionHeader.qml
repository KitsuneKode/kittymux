// A section: the space's name (its project hue as a small dot: identity, not state) or the state group's name, and how many tabs it holds.
import QtQuick
import qs.config

Item {
    id: sec
    property string label: ""
    property string hue: ""
    property int count: 0
    implicitHeight: Theme.sectionH

    Row {
        anchors.left: parent.left; anchors.leftMargin: Theme.s3
        anchors.bottom: parent.bottom; anchors.bottomMargin: 6
        spacing: 7
        Rectangle {
            visible: sec.hue !== ""
            width: 6; height: 6; radius: 3
            color: sec.hue || "transparent"
            anchors.verticalCenter: parent.verticalCenter
        }
        Label { text: sec.label; size: Theme.tCaption; weight: Theme.wSemibold; color: Theme.text2; elide: Text.ElideNone }
    }
    Label {
        anchors.right: parent.right; anchors.rightMargin: Theme.s3
        anchors.bottom: parent.bottom; anchors.bottomMargin: 6
        text: String(sec.count)
        size: Theme.tCaption; color: Theme.text3; tabular: true; elide: Text.ElideNone
    }
}
