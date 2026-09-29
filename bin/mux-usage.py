#!/usr/bin/env python3
"""mux-usage.py — agent CLI usage HUD overlay.

Loads every collector in <kittymux>/python/collectors/*.py and renders
their rows in one animated panel. Collectors are pure local-file reads
(no provider CLI spawns, no network) unless they implement live() and
KITTYMUX_USAGE_LIVE=1 is set. Results cached 60s in
$KITTYMUX_STATE/agent-usage.json so repeat invocations render instantly.

Keys: r = force refresh, anything else (or timeout) dismisses.
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

_GLYPHS = {"claude": "✳", "codex": "❋", "devin": "⬡", "cursor": "➤",
           "aider": "✎", "opencode": "‹›", "gemini": "✦", "amp": "⚡",
           "crush": "♥", "grok": "✗"}


def _rgb(h: str, p: int) -> str:
    return f"\033[38;2;{int(h[0:2], 16) * p // 100};" \
           f"{int(h[2:4], 16) * p // 100};{int(h[4:6], 16) * p // 100}m"


def _bar(pct: float, w: int = 10) -> str:
    f = round(pct / 100 * w)
    return "▓" * f + "░" * (w - f)


def _bar_color(pct: float) -> str:
    return C_OK if pct < 60 else C_WARN if pct < 85 else C_BAD


def build_lines(data: dict) -> list[tuple[str, str, str]]:
    """(text, fg_hex, kind) rows; kind 'bar' renders text|bar|pct."""
    rows = [(" agent usage ", C_NAME, "")]
    for p in data["providers"]:
        name = (_GLYPHS.get(p["name"], "·") + " " + p["name"]).ljust(9)
        if not p["rows"]:
            rows.append((f"  {name} {p.get('note') or '—'}", C_DIM, ""))
            continue
        for i, r in enumerate(p["rows"]):
            label = (r.get("label") or "").ljust(6)
            if "pct" in r:
                reset = r.get("reset") or ""
                rows.append((f"  {name} {label}|{_bar(r['pct'])}|"
                             f"{r['pct']:>3.0f}%{' · ' if reset else ''}{reset}",
                             C_CLOCK if r.get("clock") else _bar_color(r["pct"]),
                             "bar"))
            else:
                rows.append((f"  {name} {label}{r.get('text', '')} "
                             f"{r.get('reset', '')}", C_TXT, ""))
            note = p.get("note") if i == 0 else None
            if note:
                t, c, k = rows[-1]
                rows[-1] = (t + f" · {note}", c, k)
            name = " " * 9
    spark = _sparkline("burn")
    if spark:
        rows.append((f"  7d burn  {spark}", C_DIM, ""))
    age = int(time.time() - data.get("ts", time.time()))
    live_tag = " · live" if data.get("live") else ""
    rows.append((f"  cached {age}s{live_tag} · r refresh", C_DIM, ""))
    return rows


def draw(rows: list[tuple[str, str, str]], p: int, cols: int, lines: int) -> None:
    w = max(len(t) for t, _, _ in rows) + 4
    x, y = (cols - w) // 2, max(1, (lines - len(rows) - 2) // 2)
    b, dim, txt = _rgb(C_BORDER, p), _rgb(C_DIM, p), _rgb(C_TXT, p)
    top = "╭" + "─" * (w - 2) + "╮"
    bot = "╰" + "─" * (w - 2) + "╯"
    out = [f"\033[{y};{x}H{b}{top}"]
    for i, (t, fg, kind) in enumerate(rows):
        body = t[:w - 4].ljust(w - 4)
        seg = f"\033[{y + 1 + i};{x}H{b}│ {out_fg(fg, p)}{body}{b}│"
        out.append(seg)
    out.append(f"\033[{y + len(rows) + 1};{x}H{b}{bot}")
    sys.stdout.write("".join(out) + "\033[0m")
    sys.stdout.flush()


def out_fg(h: str, p: int) -> str:
    return _rgb(h, p)


def main() -> None:
    collect_only = "--collect-only" in sys.argv
    if collect_only:
        get_data(force=True)
        return
    force = False
    while True:
        data = get_data(force)
        force = False
        rows = build_lines(data)
        sys.stdout.write("\033[?25l\033[2J")
        for p in range(30, 101, 35):
            draw(rows, p, os.get_terminal_size().columns,
                 os.get_terminal_size().lines)
            time.sleep(0.04)
        r, _, _ = select.select([sys.stdin], [], [], 5.0)
        if r:
            ch = sys.stdin.read(1)
            if ch in ("r", "R"):
                force = True
                continue
            break
        break
    sys.stdout.write("\033[?25h\033[2J")


if __name__ == "__main__":
    main()
