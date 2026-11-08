// Every piece of text in the client: the theme's family at a size from the scale, SF's own tracking, FreeType rendering (crisper at UI
// sizes than Qt's distance-field atlas, and it never draws a variable font blank). `tabular` sets tabular figures for numbers that change.
import QtQuick
import qs.config

Text {
    property int size: Theme.tBody
    property int weight: Theme.wRegular
    property bool tabular: false
    font.family: size >= 20 ? Theme.fontDisplay : Theme.font
    font.pixelSize: size
    font.weight: weight
    font.letterSpacing: Theme.tracking(size)
    font.features: tabular ? ({ "tnum": 1 }) : ({})
    renderType: Text.NativeRendering
    color: Theme.text
    elide: Text.ElideRight
    maximumLineCount: 1
    textFormat: Text.PlainText
}
