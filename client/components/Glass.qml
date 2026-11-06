// The client's one surface: near-black glass (the compositor blurs behind it) with a 1 px hairline. No box inside it.
import QtQuick
import qs.config

Rectangle {
    color: Theme.glass
    radius: Theme.r3
    border.width: 1
    border.color: Theme.hairline
    Behavior on color { ColorAnimation { duration: 400; easing.type: Easing.OutCubic } }
}
