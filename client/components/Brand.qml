// An agent's own mark (assets/icons/<brand>.svg, the real brand marks), drawn in one colour: the SVG is read once and tinted by setting
// its fill, so nothing is recoloured per frame. No mark: the agent's initial; no agent at all: a terminal glyph.
import QtQuick
import Quickshell.Io
import qs.config
import qs.services

Item {
    id: b

    property string brand: ""
    property string agent: ""
    property color color: Theme.text2

    FileView {
        id: svg
        path: b.brand && Feed.iconDir ? Feed.iconDir + "/" + b.brand + ".svg" : ""
        printErrors: false
    }
    // SVG wants #rrggbb: the colour's alpha goes on the Image instead (Qt writes a translucent colour as #aarrggbb).
    readonly property string fill: Qt.rgba(b.color.r, b.color.g, b.color.b, 1).toString()
    readonly property string source: svg.loaded && b.brand
        ? "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg.text().replace("<svg ", '<svg fill="' + b.fill + '" '))
        : ""

    Image {
        anchors.centerIn: parent
        visible: b.source !== ""
        width: b.width; height: b.height
        sourceSize: Qt.size(b.width * 2, b.height * 2)
        source: b.source
        opacity: b.color.a
        smooth: true
        asynchronous: false
    }
    Label {
        anchors.centerIn: parent
        visible: b.source === "" && b.agent !== ""
        text: b.agent.charAt(0).toUpperCase()
        font.family: Theme.font
        size: Theme.tCaption
        weight: Theme.wSemibold
        color: b.color
        elide: Text.ElideNone
    }
    // No agent and no brand file: a terminal outline. A private-use glyph depends on a font the row may not have.
    Item {
        anchors.centerIn: parent
        visible: b.source === "" && b.agent === ""
        width: Math.round(b.width * 0.78)
        height: Math.round(b.height * 0.66)
        Rectangle {
            anchors.fill: parent
            radius: 2
            color: "transparent"
            border.width: 1
            border.color: b.color
        }
        Rectangle {
            width: Math.max(3, Math.round(parent.width * 0.34))
            height: 2
            radius: 1
            color: b.color
            anchors.left: parent.left
            anchors.leftMargin: 3
            anchors.verticalCenter: parent.verticalCenter
        }
    }
}
