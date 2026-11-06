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
        visible: b.source === ""
        text: b.agent ? b.agent.charAt(0).toUpperCase() : ""
        font.family: b.agent ? Theme.font : Theme.fontGlyph
        size: b.agent ? Theme.tCaption : Theme.tBody
        weight: Theme.wSemibold
        color: b.color
        elide: Text.ElideNone
    }
}
