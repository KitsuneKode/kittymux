#!/usr/bin/env python3
"""mux-usage.py — agent CLI usage HUD overlay.

Loads every collector in <kittymux>/python/collectors/*.py and renders
their rows in one animated panel. Collectors are pure local-file reads
(no provider CLI spawns, no network) unless they implement live() and
KITTYMUX_USAGE_LIVE=1 is set. Results cached 60s in
$KITTYMUX_STATE/agent-usage.json so repeat invocations render instantly.

Keys: j/k/↑/↓ select, ⏎ detail, a all-rows view, h/← back,
r force refresh, q/Esc dismiss. Stays open until dismissed.
"""

import importlib.util
import json
import os
import re
import select
import sys
import time
from pathlib import Path

# -- locate the project + collectors ------------------------------------------

MUX_HOME = Path(os.environ.get(
    "KITTYMUX_HOME",
    Path(__file__).resolve().parent.parent)).resolve()
COLLECTORS = MUX_HOME / "python" / "collectors"
sys.path.insert(0, str(COLLECTORS))  # collectors import _common from here

import _common as C  # noqa: E402

# Preferred display order; unknown collectors sort alphabetically after.
_ORDER = ["codex", "claude", "cursor", "devin"]


def load_collectors() -> list:
    """Import every collectors/*.py except _-prefixed helpers."""
    mods = []
    for f in sorted(COLLECTORS.glob("*.py")):
        if f.stem.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(f.stem, f)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if callable(getattr(mod, "collect", None)):
                mods.append(mod)
        except Exception:  # a broken collector never kills the HUD
            continue
    return mods


def _record_history(providers: list) -> None:
    today = time.strftime("%Y-%m-%d")
    try:
        hist = json.loads(C.HIST.read_text())
    except (OSError, json.JSONDecodeError):
        hist = {}
    day = hist.setdefault(today, {})
    for p in providers:
        if p["name"] == "claude":
            for r in p["rows"]:
                if r["label"] == "week":
                    m = re.match(r"([\d.]+)([MGk]?) tok", r.get("text", ""))
                    if m:
                        day["claude_fresh"] = float(m.group(1)) * (
                            1e9 if m.group(2) == "G" else 1e6 if m.group(2) == "M"
                            else 1e3 if m.group(2) == "k" else 1)
        if p["name"] == "devin":
            for r in p["rows"]:
                if r["label"] == "today":
                    m = re.search(r"([\d.]+)([MGk]?) tok", r.get("text", ""))
                    if m:
                        day["devin_tok"] = float(m.group(1)) * (
                            1e9 if m.group(2) == "G" else 1e6 if m.group(2) == "M"
                            else 1e3 if m.group(2) == "k" else 1)
    day["burn"] = sum(day.get(k, 0) for k in ("claude_fresh", "devin_tok"))
    C.write_private(C.HIST, json.dumps(hist))


def _sparkline(hist_key: str) -> str:
    try:
        hist = json.loads(C.HIST.read_text())
    except (OSError, json.JSONDecodeError):
        return ""
    days = sorted(hist)[-7:]
    vals = [float(hist[d].get(hist_key) or 0) for d in days]
    if not vals or max(vals) == 0:
        return ""
    blocks = "▁▂▃▄▅▆▇█"
    return "".join(blocks[min(7, round(v / max(vals) * 7))] for v in vals)


def collect() -> dict:
    providers = []
    mods = load_collectors()
    for mod in mods:
        try:
            providers.append(mod.collect())
        except Exception:
            providers.append({"name": mod.__name__, "rows": [],
                              "note": "collector error"})
    providers.sort(key=lambda p: (
        _ORDER.index(p["name"]) if p["name"] in _ORDER else len(_ORDER),
        p["name"]))
    _record_history(providers)

    live = {}
    if C.LIVE:
        try:
            cached = json.loads(C.CACHE.read_text()).get("live", {})
        except (OSError, json.JSONDecodeError):
            cached = {}
        # Opt-in network refresh — only collectors that implement live().
        # Module stem is the provider key: claude.py -> "claude".
        for mod in mods:
            live_fn = getattr(mod, "live", None)
            if not callable(live_fn):
                continue
            name = mod.__name__.rsplit(".", 1)[-1]
            result = live_fn(cached.get(name, {}))
            if result and result.get("rows"):
                live[name] = result
                provider = next((p for p in providers if p["name"] == name), None)
                if provider:
                    provider["rows"] = [r for r in provider["rows"]
                                        if r["label"] != "5h"]
                    provider["rows"] = result["rows"] + provider["rows"]
    return {"ts": time.time(), "providers": providers, "live": live}


def get_data(force: bool) -> dict:
    if not force and C.CACHE.is_file():
        try:
            d = json.loads(C.CACHE.read_text())
            if time.time() - d.get("ts", 0) < C.TTL:
                return d
        except (json.JSONDecodeError, OSError):
            pass
    d = collect()
    C.write_private(C.CACHE, json.dumps(d))
    return d


# ---------- render ----------

C_BORDER, C_DIM, C_TXT, C_NAME = "45475a", "6c7086", "cdd6f4", "89b4fa"
C_OK, C_WARN, C_BAD, C_CLOCK = "a6e3a1", "f9e2af", "f38ba8", "cba6f7"

_GLYPHS = {"claude": "\ue0d8", "codex": "\ue0d9",
           "cursor": "\ue0da", "gemini": "\ue0db",
           "opencode": "\ue0dc", "amp": "\ue0dd",
           "devin": "\ue0de",
           "aider": "✎", "crush": "♥", "grok": "✗"}


def _rgb(h: str, p: int) -> str:
    return f"\033[38;2;{int(h[0:2], 16) * p // 100};" \
           f"{int(h[2:4], 16) * p // 100};{int(h[4:6], 16) * p // 100}m"


def _bar(pct: float, w: int = 10) -> str:
    f = round(pct / 100 * w)
    return "▓" * f + "░" * (w - f)


def _bar_color(pct: float) -> str:
    return C_OK if pct < 60 else C_WARN if pct < 85 else C_BAD


def _live_tag(data: dict) -> str:
    return " · live" if any(v.get("rows") for v in (data.get("live") or {}).values()
                           if isinstance(v, dict)) else ""


def _headline(p: dict) -> tuple[list[dict], dict | None]:
    """Split a provider's rows into quota rows and the headline text row."""
    pcts = [r for r in p["rows"] if "pct" in r]
    texts = [r for r in p["rows"] if "pct" not in r]
    return pcts, (texts[0] if texts else None)


def build_summary(data: dict, sel: int) -> list[tuple[str, str]]:
    """One scannable row per provider; sel marks the focused row with ▸."""
    age = int(time.time() - data["ts"])
    rows = [(f" agent usage · cached {age}s{_live_tag(data)} ", C_NAME), ("", C_DIM)]
    for i, p in enumerate(data["providers"]):
        mark = "▸" if i == sel else " "
        name = (_GLYPHS.get(p["name"], "·") + " " + p["name"]).ljust(10)
        pcts, text = _headline(p)
        if not pcts:
            tail = (text or {}).get("text") or p.get("note") or "—"
            rows.append((f" {mark} {name} {tail}", C_DIM))
            continue
        r0 = pcts[0]
        tail = f"{r0['label']}"
        if r0.get("reset"):
            tail += f" · {r0['reset']}"
        for r in pcts[1:2]:
            tail += f" · {r['label']} {r['pct']:.0f}%"
        color = C_CLOCK if r0.get("clock") else _bar_color(r0["pct"])
        rows.append((f" {mark} {name} |{_bar(r0['pct'], 8)}| {r0['pct']:>3.0f}% {tail}", color))
    spark = _sparkline("burn")
    if spark:
        rows.append((f"   7d burn  {spark}", C_DIM))
    rows.append(("", C_DIM))
    rows.append((" j/k move · ⏎ detail · a all · r refresh · q", C_DIM))
    return rows


def build_detail(p: dict) -> list[tuple[str, str]]:
    """All rows for one provider — the old dense section, scoped down."""
    name = _GLYPHS.get(p["name"], "·") + " " + p["name"]
    rows = [(f" {name} ", C_NAME), ("", C_DIM)]
    for r in p["rows"]:
        if "pct" in r:
            reset = f" · {r['reset']}" if r.get("reset") else ""
            color = C_CLOCK if r.get("clock") else _bar_color(r["pct"])
            rows.append((f"   {r['label']:<7} |{_bar(r['pct'])}| {r['pct']:.0f}%{reset}", color))
        else:
            rows.append((f"   {r['label']:<7} {r.get('text', '')}", C_TXT))
    if not p["rows"]:
        rows.append((f"   {p.get('note') or '—'}", C_DIM))
    if p.get("note") and p["rows"]:
        rows.append((f"   {p['note']}", C_DIM))
    spark = _sparkline(f"{p['name']}_burn") or _sparkline("burn")
    if spark:
        rows.append((f"   7d      {spark}", C_DIM))
    rows.append(("", C_DIM))
    rows.append((" h/← back · r refresh · q", C_DIM))
    return rows


def build_all(data: dict) -> list[tuple[str, str]]:
    """The classic dense dump — everything at once, one key away."""
    rows = [(f" agent usage · all{_live_tag(data)} ", C_NAME), ("", C_DIM)]
    for p in data["providers"]:
        name = (_GLYPHS.get(p["name"], "·") + " " + p["name"]).ljust(10)
        if not p["rows"]:
            rows.append((f"   {name} {p.get('note') or '—'}", C_DIM))
            continue
        for i, r in enumerate(p["rows"]):
            note = f" · {p['note']}" if i == 0 and p.get("note") else ""
            if "pct" in r:
                reset = f" · {r['reset']}" if r.get("reset") else ""
                color = C_CLOCK if r.get("clock") else _bar_color(r["pct"])
                rows.append((f"   {name} {r['label']} |{_bar(r['pct'])}| {r['pct']:.0f}%{reset}{note}",
                             color))
            else:
                rows.append((f"   {name} {r['label']} {r.get('text', '')}{note}", C_TXT))
    spark = _sparkline("burn")
    if spark:
        rows.append((f"   7d burn  {spark}", C_DIM))
    rows.append(("", C_DIM))
    rows.append((" a summary · r refresh · q", C_DIM))
    return rows


_last_box = [0, 0, 0, 0]  # top, left, w, h of the previous frame


def draw(rows: list[tuple[str, str]], p: int, cols: int, lines: int) -> None:
    w = max(len(t) for t, _ in rows) + 2
    left = max((cols - w - 2) // 2, 0)
    n = min(len(rows), max(0, lines - 4))
    top = max((lines - n - 3) // 2, 0)
    b = _rgb(C_BORDER, p)
    pt, pl, pw, ph = _last_box
    if ph:
        # erase the previous frame's footprint so smaller boxes leave no trail
        blank = " " * pw
        out = [f"\033[{pt + i};{pl}H{blank}" for i in range(ph)]
    else:
        out = []
    out.append(f"\033[{top};{left}H{b}╭{'─' * w}╮")
    for i, (text, fg) in enumerate(rows[:n]):
        out.append(f"\033[{top + 1 + i};{left}H{b}│{_rgb(fg, p)}{text.ljust(w)}{b}│")
    out.append(f"\033[{top + 1 + n};{left}H{b}╰{'─' * w}╯")
    _last_box[:] = [top, left, w + 2, n + 2]
    sys.stdout.write("".join(out) + "\033[0m")
    sys.stdout.flush()


def _read_key() -> str:
    """One key → name; arrows collapse to names, bare Esc → esc."""
    ch = os.read(sys.stdin.fileno(), 1)
    if not ch:
        return "q"
    if ch != b"\x1b":
        return ch.decode("utf-8", "replace")
    r, _, _ = select.select([sys.stdin], [], [], 0.04)
    if not r:
        return "esc"
    rest = os.read(sys.stdin.fileno(), 2)
    return {"[A": "up", "[B": "dn", "[C": "rt", "[D": "lt"}.get(rest.decode("ascii", ""), "esc")


def interactive(data: dict) -> None:
    import termios
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        termios.tcsetattr(fd, termios.TCSANOW,
                          termios.tcgetattr(fd)[:3] + [termios.tcgetattr(fd)[3] & ~termios.ECHO & ~termios.ICANON] +
                          termios.tcgetattr(fd)[4:])
        mode, sel = "summary", 0
        cols, lines = os.get_terminal_size()
        sys.stdout.write("\033[?25l")
        for p_ in (20, 45, 70, 100):
            draw(build_summary(data, sel), p_, cols, lines)
            time.sleep(0.03)
        dirty_ts = 0.0
        while True:
            r, _, _ = select.select([sys.stdin], [], [], 1.0)
            cols, lines = os.get_terminal_size()
            if r:
                k = _read_key()
                if k in ("q", "\x03"):
                    break
                if k == "esc":
                    if mode != "summary":
                        mode = "summary"
                    else:
                        break
                elif k in ("up", "k") and mode == "summary":
                    sel = max(0, sel - 1)
                elif k in ("dn", "j") and mode == "summary":
                    sel = min(len(data["providers"]) - 1, sel + 1)
                elif k in ("\r", "\n", "rt", "l") and mode == "summary":
                    mode = "detail"
                elif k in ("lt", "h") and mode == "detail":
                    mode = "summary"
                elif k == "a":
                    mode = "summary" if mode == "all" else "all"
                elif k == "r":
                    data = get_data(force=True)
                    sel = min(sel, len(data["providers"]) - 1)
            elif time.time() - data["ts"] > C.TTL and dirty_ts != data["ts"]:
                dirty_ts = data["ts"]
                data = get_data(force=False)
            rows = (build_summary(data, sel) if mode == "summary"
                    else build_detail(data["providers"][sel]) if mode == "detail"
                    else build_all(data))
            draw(rows, 100, cols, lines)
    finally:
        termios.tcsetattr(fd, termios.TCSANOW, old)
        sys.stdout.write("\033[?25h\033[0m")


def main() -> None:
    if "--collect-only" in sys.argv:
        # quiet refresh for tab_bar's quota warning — no UI, no tty needed
        get_data(force=True)
        return
    data = get_data(force=False)
    if "--once" in sys.argv:
        for text, fg in build_all(data):
            print(f"{_rgb(fg, 100)}{text}")
        print("\033[0m", end="")
        return
    sys.stdin = open("/dev/tty", "rb", buffering=0)
    interactive(data)


if __name__ == "__main__":
    main()
