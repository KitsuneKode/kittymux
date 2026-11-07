// A number whose digits roll like an odometer when it changes (NumberFlow's idea; kuwai's RollingNumber): each digit is a column of
// 0-9 on its own spring, taking the short way round. Tabular figures and a fixed column width, so the number never changes width
// while it rolls. Reduced motion: the digits just change.
import QtQuick
import qs.config

Row {
    id: num

    property real value: 0
    property string suffix
    property int size: Theme.tCaption
    property int weight: Theme.wMedium
    property color color: Theme.text2

    readonly property string digits: String(Math.max(0, Math.round(value)))

    // Laid out right to left: the suffix first (rightmost), then the digits from the units up, so a new leading digit does not
    // re-roll the others.
    layoutDirection: Qt.RightToLeft
    Label { visible: num.suffix !== ""; text: num.suffix; size: num.size; weight: num.weight; color: num.color; elide: Text.ElideNone }

    TextMetrics { id: zero; text: "0"; font.family: Theme.font; font.pixelSize: num.size; font.features: ({ "tnum": 1 }) }

    Repeater {
        model: num.digits.length
        Item {
            id: col
            required property int index
            readonly property int digit: Number(num.digits.charAt(num.digits.length - 1 - index))
            width: Math.ceil(zero.advanceWidth)
            height: Math.ceil(zero.height)
            clip: true
            LayoutMirroring.enabled: false
            Spring { id: roll; tier: ({ stiffness: 933, damping: 60 }); epsilon: 0.002; target: col.digit; Component.onCompleted: settle() }
            Repeater {
                model: 10
                Label {
                    required property int index
                    readonly property real off: ((10 + index - roll.value) % 10 + 10) % 10
                    y: (off > 5 ? off - 10 : off) * col.height
                    visible: Math.abs(y) < col.height
                    text: String(index)
                    size: num.size; weight: num.weight; color: num.color; tabular: true
                    elide: Text.ElideNone
                }
            }
        }
    }
}
