#!/usr/bin/env python3
# kittymux layout — per-kitty-instance tab bar layout you can switch on the fly.
#
# Kitty options belong to a *process*, so the unit here is one kitty instance (all of
# its OS windows share it). The layout — edge, mode, width — lives in
# $KITTYMUX_STATE/layout-<kitty pid>.json and is applied by kitty itself through
#
#     geninclude /path/to/kittymux_layout.py        (last include in kitty.conf)
#
# which kitty runs on every (re)load and whose stdout it treats as config. That is what
# makes the choice survive `reload config` — no more "override lost on next reload".
# New instances start from layout-default.json (`kittymux layout default`), else BUILTIN.
#
# Pure Python, no kitty imports: unit-tested under system python3.

import json
import os
import sys
import tempfile
from dataclasses import asdict, dataclass

EDGES = ("left", "right", "bottom", "top")
MODES = ("full", "compact", "hidden")
WIDTH_MIN, WIDTH_MAX, WIDTH_STEP = 8, 60, 2      # tab_title_max_length; bar cols = value + 8
COMPACT_WIDTH = 1                                # → a 9-column rail
DEFAULT_WIDTH = 20                               # → 28 columns (kitty's own default)


@dataclass(frozen=True)
class Layout:
    edge: str = "left"
    mode: str = "full"
    width: int = DEFAULT_WIDTH

    def normalized(self) -> "Layout":
        edge = self.edge if self.edge in EDGES else "left"
        mode = self.mode if self.mode in MODES else "full"
        try:
            width = int(self.width)
        except (TypeError, ValueError):
            width = DEFAULT_WIDTH
        return Layout(edge, mode, max(WIDTH_MIN, min(WIDTH_MAX, width)))


BUILTIN = Layout("left", "full", DEFAULT_WIDTH)

PRESETS: dict[str, tuple[Layout, str]] = {
    "sidebar":       (Layout("left", "full"),                "vertical list: title, branch, status"),
    "rail":          (Layout("left", "compact"),             "slim icon rail — logo, 4-char title, status"),
    "right-sidebar": (Layout("right", "full"),               "the sidebar on the right edge"),
    "bottom":        (Layout("bottom", "full"),              "classic horizontal bar at the bottom"),
    "top":           (Layout("top", "full"),                 "horizontal bar at the top"),
    "zen":           (Layout("left", "hidden"),              "hide the bar entirely (toggle back any time)"),
}


def is_vertical(layout: Layout) -> bool:
    return layout.edge in ("left", "right")


def render_conf(layout: Layout) -> str:
    """kitty config text for a layout (this is what geninclude prints)."""
    lay = layout.normalized()
    lines = [f"tab_bar_edge {lay.edge}"]
    if lay.mode == "hidden":
        lines.append("tab_bar_min_tabs 9999")                     # never enough tabs → bar hidden
    else:
        lines.append("tab_bar_min_tabs 2")
        if is_vertical(lay):
            lines.append("tab_title_max_length %d" % (COMPACT_WIDTH if lay.mode == "compact" else lay.width))
        else:
            lines.append("tab_title_max_length 0")
    return "\n".join(lines) + "\n"


# ── transitions ──────────────────────────────────────────────────────────────
def cycle(value: str, options: tuple, step: int = 1) -> str:
    i = options.index(value) if value in options else 0
    return options[(i + step) % len(options)]


def next_mode(layout: Layout) -> Layout:
    lay = layout.normalized()
    return Layout(lay.edge, cycle(lay.mode, MODES), lay.width)


def next_edge(layout: Layout) -> Layout:
    lay = layout.normalized()
    cycle_order = ("left", "bottom", "right")          # the classic edge cycle (top on request)
    edge = cycle(lay.edge, cycle_order) if lay.edge in cycle_order else "left"
    return Layout(edge, lay.mode, lay.width)


def adjust_width(layout: Layout, delta: int) -> Layout:
    lay = layout.normalized()
    # resizing implies you want to see the bar: leave compact/hidden for the full sidebar
    mode = "full" if lay.mode != "full" else lay.mode
    return Layout(lay.edge, mode, max(WIDTH_MIN, min(WIDTH_MAX, lay.width + delta))).normalized()


def preset(name: str) -> Layout | None:
    hit = PRESETS.get(name)
    return hit[0] if hit else None


def apply_command(layout: Layout, cmd: str, arg: str = "") -> Layout:
    """Pure state transition for `kittymux layout <cmd> [arg]`. Raises ValueError with a
    human message on bad input."""
    lay = layout.normalized()
    if cmd == "mode":
        if arg in ("", "cycle"):
            return next_mode(lay)
        if arg in MODES:
            return Layout(lay.edge, arg, lay.width)
        raise ValueError(f"mode must be one of {', '.join(MODES)} or cycle")
    if cmd == "edge":
        if arg in ("", "cycle"):
            return next_edge(lay)
        if arg in EDGES:
            return Layout(arg, lay.mode, lay.width)
        raise ValueError(f"edge must be one of {', '.join(EDGES)} or cycle")
    if cmd == "width":
        if arg[:1] in ("+", "-") and arg[1:].isdigit():
            return adjust_width(lay, int(arg))
        if arg.isdigit():
            return Layout(lay.edge, "full", int(arg)).normalized()
        raise ValueError("width takes +N, -N or a number")
    if cmd == "preset":
        hit = preset(arg)
        if hit is None:
            raise ValueError(f"unknown preset '{arg}' — choose from {', '.join(PRESETS)}")
        return hit
    raise ValueError(f"unknown layout command '{cmd}'")


def describe(layout: Layout) -> str:
    lay = layout.normalized()
    if lay.mode == "hidden":
        return f"bar hidden ({lay.edge} when shown)"
    if lay.mode == "compact":
        return f"{lay.edge} rail"
    return f"{lay.edge} bar" + (f", width {lay.width}" if is_vertical(lay) else "")


# ── drag-to-resize maths (used by kittymux_barsize) ───────────────────────────
BAR_PADDING_COLS = 8          # measured: a vertical bar is tab_title_max_length + 8 columns wide
MAX_WINDOW_FRACTION = 1 / 3   # kitty itself caps a vertical bar at a third of the window (measured: 43 of 130 cols)


def max_width_for(window_cols: int) -> int:
    """Largest tab_title_max_length whose bar fits kitty's one-third-of-the-window cap (and the hard cap)."""
    if window_cols <= 0:
        return WIDTH_MAX
    return max(WIDTH_MIN, min(WIDTH_MAX, int(window_cols * MAX_WINDOW_FRACTION) - BAR_PADDING_COLS))


def width_from_pointer(x_px: float, cell_w: float, window_px: float, edge: str) -> int:
    """tab_title_max_length for a vertical bar whose inner edge is dragged to pixel `x_px`
    (measured from the window's left edge). Clamped: never below WIDTH_MIN, never above
    the hard cap or a third of the window."""
    if cell_w <= 0:
        return DEFAULT_WIDTH
    cols = (window_px - x_px) / cell_w if edge == "right" else x_px / cell_w
    window_cols = int(window_px // cell_w)
    n = int(round(cols)) - BAR_PADDING_COLS
    return max(WIDTH_MIN, min(max_width_for(window_cols), n))


def in_grab_zone(x_px: float, bar_edge_px: float, cell_w: float, zone_cells: float = 0.75) -> bool:
    """Pointer close enough to the bar's inner edge to grab it."""
    return abs(x_px - bar_edge_px) <= max(1.0, cell_w * zone_cells)


# ── storage ──────────────────────────────────────────────────────────────────
def state_dir() -> str:
    return os.environ.get("KITTYMUX_STATE") or os.path.join(
        os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state"), "kittymux")


def _path(sdir: str, pid: int | None) -> str:
    return os.path.join(sdir, "layout-default.json" if pid is None else f"layout-{pid}.json")


def _read(path: str) -> Layout | None:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return Layout(data.get("edge", "left"), data.get("mode", "full"), data.get("width", DEFAULT_WIDTH)).normalized()
    except (OSError, ValueError, AttributeError):
        return None


def load(sdir: str, pid: int) -> Layout | None:
    """Instance layout → saved default → None. None means "the user never chose one":
    we then emit nothing and their own kitty.conf stays in charge (no surprise flips)."""
    return _read(_path(sdir, pid)) or _read(_path(sdir, None))


def legacy_edge(config_dir: str) -> str | None:
    """The edge a pre-layout install set via include-tab-edge.conf, if any."""
    try:
        with open(os.path.join(config_dir, "include-tab-edge.conf"), encoding="utf-8") as f:
            for line in reversed(f.read().splitlines()):
                parts = line.split()
                if len(parts) == 2 and parts[0] == "tab_bar_edge" and parts[1] in EDGES:
                    return parts[1]
    except OSError:
        pass
    return None


def base_layout(sdir: str, pid: int, config_dir: str) -> Layout:
    """What a change should start from: the saved layout, else the user's existing edge."""
    saved = load(sdir, pid)
    if saved is not None:
        return saved
    return Layout(legacy_edge(config_dir) or "bottom", "full", DEFAULT_WIDTH)


def save(sdir: str, pid: int | None, layout: Layout) -> str:
    """Atomic, private (0600) write. pid=None writes the default."""
    os.makedirs(sdir, mode=0o700, exist_ok=True)
    path = _path(sdir, pid)
    fd, tmp = tempfile.mkstemp(dir=sdir, prefix=".layout-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(asdict(layout.normalized()), f)
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return path


def cleanup_stale(sdir: str) -> int:
    """Remove layout-<pid>.json for kitty processes that no longer exist."""
    removed = 0
    try:
        names = os.listdir(sdir)
    except OSError:
        return 0
    for name in names:
        if name.startswith("layout-") and name.endswith(".json") and name != "layout-default.json":
            try:
                pid = int(name[len("layout-"):-len(".json")])
            except ValueError:
                continue
            if not os.path.exists(f"/proc/{pid}"):
                try:
                    os.unlink(os.path.join(sdir, name))
                    removed += 1
                except OSError:
                    pass
    return removed


def kitty_pid() -> int:
    """PID of the kitty process asking for config. geninclude .py scripts run in kitty's
    embedded interpreter (getpid); a spawned script sees kitty as its parent."""
    forced = os.environ.get("KITTYMUX_LAYOUT_PID")
    if forced and forced.isdigit():
        return int(forced)
    for pid in (os.getpid(), os.getppid()):
        try:
            with open(f"/proc/{pid}/comm") as f:
                if f.read().strip().startswith("kitty"):
                    return pid
        except OSError:
            continue
    return os.getpid()


def main() -> int:
    """geninclude entry point: print this instance's layout as kitty config. Must
    return (never sys.exit): it runs in kitty's process."""
    sdir = state_dir()
    cleanup_stale(sdir)
    layout = load(sdir, kitty_pid())
    if layout is not None:                     # nothing saved → print nothing, change nothing
        sys.stdout.write(render_conf(layout))
    return 0


if __name__ == "__main__":
    # NOT `raise SystemExit`: as a geninclude script this runs inside kitty's own
    # interpreter, where SystemExit would quit kitty itself.
    main()
