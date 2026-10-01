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


# ── options that only exist in newer kitty ───────────────────────────────────
# A kitty that does not know an option reports a config error on every reload, and the kitty RUNNING
# on this machine may be older than the files on disk (a package update under a live session). So
# these lines are emitted only when the version of the kitty process asking says it understands them.
DETECT_URL_MIN = (0, 49, 2)          # detect_url_regex
DIM_SHADER_MIN = (0, 49, 2)          # dim-inactive-windows stopped dimming the tab bar here (custom_shaders itself is 0.49.0)
DIM_FLAG = "dim-inactive"            # $KITTYMUX_STATE/dim-inactive present → dim the windows that are not focused


# POSIX-ERE for `path/to/file.py:42[:7]`; kittymux_openref.DETECT_REGEX must stay identical (a unit test pins it —
# this file runs as a geninclude script and cannot import its neighbours)
DETECT_URL_REGEX = r"[[:alnum:]_./~-]+\.[[:alnum:]]+:[0-9]+(:[0-9]+)?"


def have_slangc(env=None) -> bool:
    """kitty compiles custom shaders with the slang compiler (`slangc`, or $SLANGC): without it every reload logs a failure."""
    import shlex
    import shutil
    env = os.environ if env is None else env
    try:
        argv = shlex.split(env.get("SLANGC") or "slangc")
    except ValueError:
        return False
    return bool(argv) and shutil.which(argv[0]) is not None


def gated_conf(version: tuple, sdir: str, slangc: bool = False) -> str:
    """Config lines for features the asking kitty supports. `version` is that kitty's (major, minor, patch);
    `slangc` says the shader compiler is installed (custom shaders cannot build without it)."""
    lines = []
    if version >= DETECT_URL_MIN:
        lines.append(f"detect_url_regex {DETECT_URL_REGEX}")
    if version >= DIM_SHADER_MIN and slangc and os.path.exists(os.path.join(sdir, DIM_FLAG)):
        lines.append("custom_shaders dim-inactive-windows")
    return "".join(line + "\n" for line in lines)


def kitty_version() -> tuple:
    """(major, minor, patch) of the kitty asking for config; (0, 0, 0) when it cannot be told (nothing gated is emitted)."""
    forced = os.environ.get("KITTYMUX_KITTY_VERSION")
    if forced:
        try:
            return tuple(int(x) for x in forced.split(".")[:3])
        except ValueError:
            return (0, 0, 0)
    try:
        from kitty.constants import version        # only importable inside kitty's own interpreter
        return tuple(version)
    except Exception:
        return (0, 0, 0)


# ── transitions ──────────────────────────────────────────────────────────────
def cycle(value: str, options: tuple, step: int = 1) -> str:
    i = options.index(value) if value in options else 0
    return options[(i + step) % len(options)]


def next_mode(layout: Layout) -> Layout:
    lay = layout.normalized()
    return Layout(lay.edge, cycle(lay.mode, MODES), lay.width)


def next_edge(layout: Layout) -> Layout:
    lay = layout.normalized()
    edge = cycle(lay.edge, ("left", "bottom", "top", "right"))
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


COMPACT_MAX_COLS = 12       # a vertical bar at most this wide is the slim rail (one-line rows)
TOGGLE_CELLS = 5            # the collapse/expand button: its hit area starts this many cells from the bar's inner edge
HEADER_ROWS = 2             # the header is two rows tall (a ~44 px target, like a touch button) when the bar is tall enough
HEADER_MIN_LINES = 8
GRAB_CELLS = 1.5            # resize grab zone: this many cells inside the bar's inner edge (kitty sends the bar nothing outside it)


def header_rows(bar_lines: int, max_title_lines: int, compact: bool = False) -> int:
    """Rows of the first tab's header: two when the bar is tall enough AND kitty lets a tab be tall enough.
    kitty caps every tab's height at `tab_title_max_lines`; a tab that draws more spills into the blank
    spacer row (no gap, no divider), so the header must fit inside the cap: header + title + subtitle."""
    needed = 3 if compact else 4
    return HEADER_ROWS if bar_lines >= HEADER_MIN_LINES and max_title_lines >= needed else 1


def toggle_collapsed(layout: Layout) -> Layout:
    """The sidebar's collapse button: full → slim rail, rail or hidden → full (width kept)."""
    lay = layout.normalized()
    return Layout(lay.edge, "compact" if lay.mode == "full" else "full", lay.width)


def in_toggle_zone(x_px: float, y_px: float, left: float, right: float, top: float,
                   cell_w: float, cell_h: float, compact: bool, rows: int = HEADER_ROWS, slop: float = 0.0) -> bool:
    """Pointer on the collapse/expand button: the header (`rows` rows) of a vertical bar, the last
    TOGGLE_CELLS cells (the whole width on the slim rail). It stops short of the inner edge so the
    resize grab zone keeps working there. `slop` grows the zone (px) on every side but that edge:
    used for the release, so a press that wobbled a little still counts."""
    if not (top - slop <= y_px < top + rows * cell_h + slop):
        return False
    start = (left if compact else right - TOGGLE_CELLS * cell_w) - slop
    return start <= x_px < right - GRAB_CELLS * cell_w


def in_grab_zone(x_px: float, bar_edge_px: float, cell_w: float, zone_cells: float = GRAB_CELLS) -> bool:
    """Pointer close enough to the bar's inner edge to grab it."""
    return abs(x_px - bar_edge_px) <= max(1.0, cell_w * zone_cells)


# ── vertical-bar hit testing (used by kittymux_barsize) ───────────────────────
def drag_target(extents, dragged_id: int, target_id: int, row: float) -> int:
    """Which tab counts as "under the pointer" while `dragged_id` is being dragged. kitty swaps the dragged
    tab with whatever tab is under the pointer the moment it touches ANY of its rows; with tabs of different
    heights each swap shifts the layout under the pointer and the order cascades. So a tab only counts once
    the pointer has passed its MIDPOINT in the direction of travel; before that the dragged tab itself does
    (kitty then does nothing). `extents` is [(tab_id, first_row, last_row)] in the current order; `row` is the
    pointer's row as a float (rows span [first, last + 1))."""
    if not target_id or target_id <= 0 or target_id == dragged_id:
        return target_id
    order = [e[0] for e in extents]
    if dragged_id not in order or target_id not in order:
        return target_id
    first, last = next((a, b) for t, a, b in extents if t == target_id)
    mid = (first + last + 1) / 2
    below = order.index(target_id) > order.index(dragged_id)
    passed = row >= mid if below else row < mid
    return target_id if passed else dragged_id



def snap_tab_id(extents, row: int) -> int:
    """Tab id for a pointer on `row` of a vertical bar, forgiving the blank spacer lines kitty puts
    between tabs. `extents` is [(tab_id, first_row, last_row)] top to bottom.

    Kitty's own lookup only knows a tab's own rows. A pointer on a spacer row is "no tab", and while
    dragging a tab that case falls through to "swap with the LAST tab" — so a third of the positions
    in a two-line-per-tab bar threw the dragged tab to the end of the list. A row between two tabs
    belongs to the nearer one (a tie goes to the lower tab); rows above the first or below the last
    tab, and synthetic entries (id <= 0, e.g. the "+" button), stay "no tab"."""
    real = [(t, a, b) for (t, a, b) in extents if t > 0]
    if not real:
        return 0
    for t, a, b in real:
        if a <= row <= b:
            return t
    if row < real[0][1] or row > real[-1][2]:
        return 0
    for prev, nxt in zip(real, real[1:]):
        if prev[2] < row < nxt[1]:
            return prev[0] if row - prev[2] < nxt[1] - row else nxt[0]
    return 0


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


def _write(sdir: str, pid: int | None, layout: Layout) -> str:
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


def _pin_path(sdir: str) -> str:
    return os.path.join(sdir, "layout-default.pinned")


def save(sdir: str, pid: int | None, layout: Layout) -> str:
    """Save a kitty instance's layout (pid) — or the default for new windows (pid=None).
    Unless a default was pinned (`kittymux layout default`), an instance's choice also becomes the
    default, so a NEW kitty starts the way you last left one; each running kitty keeps its own."""
    path = _write(sdir, pid, layout)
    if pid is not None and not os.path.exists(_pin_path(sdir)):
        _write(sdir, None, layout)
    return path


def pin_default(sdir: str, layout: Layout) -> None:
    """Make `layout` THE default for new kitty windows, whatever any instance does later."""
    _write(sdir, None, layout)
    with open(_pin_path(sdir), "w", encoding="utf-8"):
        pass


def clear_default(sdir: str) -> None:
    """Forget the default and un-pin: new windows follow the user's kitty.conf until a layout is chosen."""
    for path in (_path(sdir, None), _pin_path(sdir)):
        try:
            os.unlink(path)
        except OSError:
            pass


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
    sys.stdout.write(gated_conf(kitty_version(), sdir, have_slangc()))
    return 0


if __name__ == "__main__":
    # NOT `raise SystemExit`: as a geninclude script this runs inside kitty's own
    # interpreter, where SystemExit would quit kitty itself.
    main()
