// Design tokens for the kittymux client. Colours come from the live kitty theme (tabs.json `palette`, built by kittymux_theme from
// kitty's own colours: no palette is typed here, only a neutral fallback until the first document arrives). The shape, type and motion
// follow kuwai's design system (docs/DESIGN.md there): near-black glass with a 1 px hairline, a small type scale with tabular digits,
// three critically damped springs (Fluid Functionalism's tiers), exits a step quicker than entrances, and motion only where it has a job.
pragma Singleton

import QtQuick
import Quickshell

Singleton {
    id: root

    // ── Colour: the live kitty theme ─────────────────────────────────────
    property var palette: ({})
    function pick(name, fallback) { return /^#[0-9a-fA-F]{6}$/.test(palette[name] || "") ? palette[name] : fallback; }
    readonly property color bg: pick("bg", "#111114")
    readonly property color fg: pick("fg", "#e8e8ea")
    readonly property color muted: pick("muted", "#9a9aa0")
    readonly property color faint: pick("faint", "#66666c")
    readonly property color accent: pick("accent", "#9a9aa0")
    readonly property color working: pick("working", "#9a9aa0")
    readonly property color waiting: pick("waiting", "#e5a050")
    readonly property color done: pick("done", "#7fbf7f")
    readonly property color alert: pick("alert", "#e06c75")
    readonly property bool lightTheme: (0.2126 * bg.r + 0.7152 * bg.g + 0.0722 * bg.b) > 0.5

    // Glass: the theme's background pulled toward black, translucent so the compositor's blur reads through (Hyprland: a layer rule on
    // the `kittymux-client` namespace, see the docs). A light theme keeps its own background: light glass, dark text.
    readonly property color glass: lightTheme ? Qt.rgba(bg.r, bg.g, bg.b, 0.82)
                                              : Qt.rgba(bg.r * 0.55, bg.g * 0.55, bg.b * 0.55, 0.78)
    readonly property color hairline: Qt.rgba(fg.r, fg.g, fg.b, lightTheme ? 0.14 : 0.09)
    readonly property color wash: Qt.rgba(fg.r, fg.g, fg.b, 0.06)          // hover
    readonly property color washHi: Qt.rgba(fg.r, fg.g, fg.b, 0.10)        // selected / keyboard
    readonly property color track: Qt.rgba(fg.r, fg.g, fg.b, 0.14)          // the empty part of a ring
    // Text over glass is a touch brighter than on a solid surface (vibrancy).
    readonly property color text: Qt.rgba(fg.r, fg.g, fg.b, 0.96)
    readonly property color text2: Qt.rgba(fg.r, fg.g, fg.b, 0.68)
    readonly property color text3: Qt.rgba(fg.r, fg.g, fg.b, 0.46)
    readonly property real accentHairline: 0.45                             // the accent mark at 45%: state colours lead

    function toneColor(name) {
        return name === "waiting" ? waiting : name === "alert" ? alert : name === "done" ? done
             : name === "text" ? text : name === "accent" ? accent : text3;
    }

    // ── Type: one family, five sizes, three weights ──────────────────────
    readonly property bool sf: Qt.fontFamilies().indexOf("SF Pro Text") >= 0
    readonly property string font: sf ? "SF Pro Text" : (Qt.fontFamilies().indexOf("Inter") >= 0 ? "Inter" : "sans-serif")
    readonly property string fontDisplay: sf && Qt.fontFamilies().indexOf("SF Pro Display") >= 0 ? "SF Pro Display" : font
    readonly property string fontGlyph: "Symbols Nerd Font"
    readonly property int tMicro: 10
    readonly property int tCaption: 11
    readonly property int tBody: 13
    readonly property int tTitle: 15
    readonly property int tHero: 20
    readonly property int wRegular: 400
    readonly property int wMedium: 500
    readonly property int wSemibold: 600
    // SF's own tracking (its trak table), which Qt does not apply; Inter tracks itself.
    readonly property var trakSizes: [10, 11, 12, 13, 14, 15, 16, 17, 20, 22, 24]
    readonly property var trakPro: [24, 12, 0, -12, -22, -32, -40, -52, -46, -24, 6]
    function tracking(px) {
        if (!sf) return 0;
        const xs = trakSizes, ys = trakPro;
        let v = ys[ys.length - 1];
        if (px <= xs[0]) v = ys[0];
        else for (let k = 1; k < xs.length; k++)
            if (px <= xs[k]) { v = ys[k - 1] + (ys[k] - ys[k - 1]) * (px - xs[k - 1]) / (xs[k] - xs[k - 1]); break; }
        return v / 2048 * px;
    }

    // ── Shape and space ──────────────────────────────────────────────────
    readonly property int r1: 8
    readonly property int r2: 12
    readonly property int r3: 18
    readonly property int s1: 4
    readonly property int s2: 8
    readonly property int s3: 12
    readonly property int s4: 16
    readonly property int rowH: 46
    readonly property int sectionH: 28
    readonly property int mark: 26

    // ── Motion ───────────────────────────────────────────────────────────
    // Springs per unit mass, critically damped: fast 0.08 s (highlights), moderate 0.16 s (things that must land), slow 0.24 s (a
    // surface). Exits are tweens a tier quicker. UI motion stays under 300 ms; the working ring steps a quarter turn every 3 s and rests between steps.
    readonly property var springFast: ({ stiffness: 13300, damping: 231, exitMs: 60 })
    readonly property var springModerate: ({ stiffness: 3329, damping: 115, exitMs: 120 })
    readonly property var springSlow: ({ stiffness: 1069, damping: 57.5, exitMs: 160 })
    readonly property int hoverMs: 80
    readonly property int pressMs: 140
    readonly property int enterMs: 200
    readonly property int exitMs: 150
    readonly property int stepMs: 3000          // the working ring: a quarter turn this often (the bar and the panel use the same period)
    readonly property int stepGlideMs: 600      // ...gliding this long, then at rest
    readonly property real pressScale: 0.985
    // Reduced motion: KITTYMUX_REDUCE_MOTION=1 (or the desktop's own switch, passed the same way). Fades and colour stay;
    // travel, glides, scale and turning go.
    readonly property bool reduceMotion: (Quickshell.env("KITTYMUX_REDUCE_MOTION") || "") === "1"
}
