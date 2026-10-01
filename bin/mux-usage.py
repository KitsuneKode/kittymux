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
import queue
import re
import select
import signal
import sys
import threading
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


# ---------- progressive loader ------------------------------------------------
# Collectors run one thread each; the overlay paints a skeleton instantly and
# merges rows as they land. Order is fixed so rows never jump — a provider's
# content just fills in. Live fetches (the slow tail) run in parallel and
# merge last. Anything still pending past STUCK_S is reported "timed out".

STUCK_S = 10.0
_SPIN = "◐◓◑◒"


def _skeleton(name: str) -> dict:
    return {"name": name, "rows": [], "note": "scanning…", "pending": True}


def _apply_live(p: dict, lv: dict) -> None:
    # _live markers make re-merging idempotent: a refresh replaces the old
    # live rows in place instead of stacking duplicates.
    p["rows"] = [r for r in p["rows"]
                 if not r.get("_live") and r["label"] != "5h"]
    p["rows"] = [dict(r, _live=1) for r in lv["rows"]] + p["rows"]


def _sanitise(d: dict) -> dict:
    return {"ts": d["ts"], "live": d.get("live") or {},
            "providers": [
                {k: ([{rk: rv for rk, rv in r.items() if not rk.startswith("_")}
                      for r in v] if k == "rows" else v)
                 for k, v in p.items()
                 if not k.startswith("_") and k != "pending"}
                for p in d["providers"]]}


class Loader:
    """Fan-out collector threads; UI drains .q between keypresses."""

    def __init__(self, mods: list) -> None:
        self.mods = mods
        self.q: queue.Queue = queue.Queue()
        self.pending: set[str] = set()
        self.live_pending: set[str] = set()
        self.since: dict[str, float] = {}
        self.local_done = False

    def alive(self) -> bool:
        return bool(self.pending or self.live_pending)

    def start(self, live: bool) -> None:
        now = time.time()
        for mod in self.mods:
            name = mod.__name__.rsplit(".", 1)[-1]
            self.pending.add(name)
            self.since[name] = now
            threading.Thread(target=self._run_local, args=(name, mod.collect),
                             daemon=True).start()
        if live:
            try:
                cached = json.loads(C.CACHE.read_text()).get("live", {})
            except (OSError, json.JSONDecodeError):
                cached = {}
            for mod in self.mods:
                live_fn = getattr(mod, "live", None)
                if not callable(live_fn):
                    continue
                name = mod.__name__.rsplit(".", 1)[-1]
                self.live_pending.add(name)
                self.since[name] = now
                threading.Thread(target=self._run_live,
                                 args=(name, live_fn, cached.get(name) or {}),
                                 daemon=True).start()

    def _run_local(self, name: str, fn) -> None:
        try:
            res = fn()
        except Exception as e:  # a broken collector never kills the HUD
            res = {"name": name, "rows": [], "note": "error",
                   "err": str(e)[:48] or type(e).__name__}
        self.q.put(("local", name, res))

    def _run_live(self, name: str, fn, cached: dict) -> None:
        try:
            res = fn(cached)
        except Exception:
            res = cached
        self.q.put(("live", name, res or {}))


def _provider_order(mods: list) -> list[str]:
    names = [m.__name__.rsplit(".", 1)[-1] for m in mods]
    return [n for n in _ORDER if n in names] + \
        sorted(n for n in names if n not in _ORDER)


def _seed(live: bool, mods: list) -> tuple[dict, "Loader"]:
    """Best instant state: fresh cache → done; stale cache → paint it while a
    loader refreshes; no cache → skeletons."""
    names = _provider_order(mods)
    data = {"ts": 0.0, "providers": [_skeleton(n) for n in names], "live": {}}
    loader = Loader(mods)
    try:
        cached = json.loads(C.CACHE.read_text())
    except (OSError, json.JSONDecodeError):
        cached = None
    if cached and time.time() - cached.get("ts", 0) < C.TTL:
        return cached, loader  # fresh — nothing to load
    if cached and cached.get("providers"):
        by_name = {p.get("name"): p for p in cached["providers"]
                   if isinstance(p, dict)}
        data["providers"] = [by_name.get(n) or _skeleton(n) for n in names]
        data["ts"] = cached["ts"]
        data["live"] = cached.get("live") or {}
    loader.start(live)
    return data, loader


def _drain(loader: Loader, data: dict) -> None:
    """Apply everything the loader delivered; mark stuck collectors."""
    changed = False
    while True:
        try:
            kind, name, res = loader.q.get_nowait()
        except queue.Empty:
            break
        changed = True
        p = next((x for x in data["providers"] if x["name"] == name), None)
        if kind == "local":
            loader.pending.discard(name)
            if p is not None:
                p.clear()
                p.update(res)
            lv = (data["live"] or {}).get(name)
            if p is not None and lv and lv.get("rows"):
                _apply_live(p, lv)
        else:
            loader.live_pending.discard(name)
            if res.get("rows"):
                data.setdefault("live", {})[name] = res
                if p is not None and not p.get("pending"):
                    _apply_live(p, res)
    now = time.time()
    for name in list(loader.pending):
        if now - loader.since.get(name, now) > STUCK_S:
            loader.pending.discard(name)
            p = next((x for x in data["providers"] if x["name"] == name), None)
            if p is not None:
                p.clear()
                p.update({"name": name, "rows": [], "note": "timed out",
                          "err": "took too long"})
            changed = True
    for name in list(loader.live_pending):
        if now - loader.since.get(name, now) > STUCK_S + 2:
            loader.live_pending.discard(name)
            changed = True
    if changed:
        if not loader.pending and not loader.local_done:
            loader.local_done = True
            data["ts"] = time.time()
            _record_history(data["providers"])
        C.write_private(C.CACHE, json.dumps(_sanitise(data)))


# ---------- render ----------

# UI chrome follows the live kitty theme; provider brand colours stay fixed.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "python"))
import kittymux_theme  # noqa: E402

_PAL = kittymux_theme.palette_from_kitty()


def _h(rgb: int) -> str:
    return f"{rgb & 0xFFFFFF:06x}"


C_BORDER, C_DIM, C_TXT, C_NAME = _h(_PAL.line), _h(_PAL.faint), _h(_PAL.text), _h(_PAL.info)
C_OK, C_WARN, C_BAD, C_CLOCK = _h(_PAL.done), _h(_PAL.waiting), _h(_PAL.alert), _h(_PAL.accent)

_GLYPHS = {"claude": "\ue0d8", "codex": "\ue0d9",
           "cursor": "\ue0da", "gemini": "\ue0db",
           "opencode": "\ue0dc", "amp": "\ue0dd",
           "devin": "\ue0de",
           "aider": "✎", "crush": "♥", "grok": "✗"}


# Brand accent per provider — names/glyphs get this; values keep severity.
_BRAND = {"claude": "d97757", "codex": "10a37f", "cursor": "5b8ef4",
          "devin": "8b5cf6", "gemini": "4796e3", "opencode": "9ca3af",
          "amp": "f59e0b"}
_TRACK = "313244"  # unfilled bar segment
_ELAPSED = "585b70"  # window-elapsed fill (surface2)
_SEGS = ("a6e3a1", "f9e2af", "cba6f7", "f38ba8")  # spend-stack colors


def _rgb(h: str, p: int) -> str:
    return f"\033[38;2;{int(h[0:2], 16) * p // 100};" \
           f"{int(h[2:4], 16) * p // 100};{int(h[4:6], 16) * p // 100}m"


def _bg(h: str) -> str:
    return f"\033[48;2;{int(h[0:2], 16)};{int(h[2:4], 16)};{int(h[4:6], 16)}m"


_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _vlen(s: str) -> int:
    return len(_ANSI_RE.sub("", s))


def _pad(s: str, w: int) -> str:
    return s + " " * max(0, w - _vlen(s))


def _trunc(s: str, w: int) -> str:
    """ANSI-aware hard truncate — escapes pass through, visible cells capped."""
    out, n, i = [], 0, 0
    while i < len(s) and n < w:
        if s[i] == "\x1b":
            m = _ANSI_RE.match(s, i)
            if m:
                out.append(m.group(0))
                i = m.end()
                continue
        out.append(s[i])
        n += 1
        i += 1
    return "".join(out)


def _sev(r: dict) -> str:
    """maxed → at/over the cap; high → ≥80%; warn → ≥60%; ok otherwise."""
    pct = r.get("pct")
    if not isinstance(pct, (int, float)):
        return "ok"
    return "maxed" if pct >= 95 else "high" if pct >= 80 \
        else "warn" if pct >= 60 else "ok"


def _maxed(providers: list) -> list[str]:
    """Providers with at least one exhausted quota."""
    return [p["name"] for p in providers
            if any(_sev(r) == "maxed" for r in p["rows"])]


def _bar_color(pct: float) -> str:
    return C_OK if pct < 60 else C_WARN if pct < 85 else C_BAD


def _bar(pct: float, w: int = 10, fill: str | None = None) -> str:
    """SGR background-color cells — no glyph dependency, always crisp."""
    f = max(0, min(w, round(min(100.0, pct) / 100 * w)))
    return _bg(fill or _bar_color(pct)) + " " * f + _bg(_TRACK) + " " * (w - f) + "\033[0m"


def _stack_bar(parts: list[float], w: int = 12) -> str:
    """Proportional segments (e.g. cursor included vs bonus spend)."""
    total = sum(parts) or 1
    out, used = [], 0
    for i, v in enumerate(parts):
        n = (w - used) if i == len(parts) - 1 else round(v / total * w)
        n = max(0, min(n, w - used))
        used += n
        out.append(_bg(_SEGS[i % len(_SEGS)]) + " " * n)
    out.append(_bg(_TRACK) + " " * (w - used))
    return "".join(out) + "\033[0m"


# Period length in seconds for rows that can show a "window elapsed" bar.
_PERIODS = {"5h": 5 * 3600, "day": 86400, "wk": 7 * 86400, "mo": 30 * 86400}
_SPARK_KEYS = {"claude": "claude_fresh", "devin": "devin_tok"}


def _week_chart(hist_key: str, brand: str) -> list[tuple[str, str]]:
    """Two-row weekly chart: weekday initials over per-day burn blocks."""
    if not hist_key:
        return []
    try:
        hist = json.loads(C.HIST.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    now = time.time()
    days = [time.strftime("%Y-%m-%d", time.localtime(now - i * 86400))
            for i in range(6, -1, -1)]
    vals = []
    for d in days:
        try:
            vals.append(float((hist.get(d) or {}).get(hist_key) or 0))
        except (TypeError, ValueError):
            vals.append(0.0)
    peak = max(vals)
    if peak == 0:
        return []
    blocks = "▁▂▃▄▅▆▇█"
    letters = " ".join("MTWTFSS"[time.strptime(d, "%Y-%m-%d").tm_wday] for d in days)
    bars = " ".join(blocks[min(7, round(v / peak * 7))] for v in vals)
    return [(f"   week    {letters}", C_DIM),
            (f"   {'':<7} {_rgb(brand, 100)}{bars}\033[0m", C_TXT)]


def _live_tag(data: dict) -> str:
    return " · live" if any(v.get("rows") for v in (data.get("live") or {}).values()
                           if isinstance(v, dict)) else ""


def _headline(p: dict) -> tuple[list[dict], dict | None]:
    """Split a provider's rows into quota rows and the headline text row."""
    pcts = [r for r in p["rows"] if "pct" in r]
    texts = [r for r in p["rows"] if "pct" not in r]
    return pcts, (texts[0] if texts else None)


def build_summary(data: dict, sel: int, status: str = "",
                  spin: str = "◐") -> list[tuple[str, str]]:
    """One scannable row per provider; sel marks the focused row with ▸."""
    age = int(time.time() - data["ts"]) if data.get("ts") else 0
    tag = status or (f"cached {age}s" if data.get("ts") else "loading")
    maxed = _maxed(data["providers"])
    badge = _rgb(C_BAD, 100) + f"✗ {'/'.join(maxed)} maxed " + "\033[0m" \
        if maxed else ""
    rows = [(f" agent usage · {badge}{tag}{_live_tag(data)} ", C_NAME),
            ("", C_DIM)]
    for i, p in enumerate(data["providers"]):
        mark = "▸" if i == sel else " "
        sev_worst = "maxed" if p["name"] in maxed else "ok"
        brand = _BRAND.get(p["name"], C_NAME)
        name = _pad(f"{_rgb(C_BAD if sev_worst == 'maxed' else brand, 100)}"
                    f"{_GLYPHS.get(p['name'], '·')} {p['name']}\033[0m", 10)
        if p.get("pending"):
            rows.append((f" {mark} {name} {spin} {p.get('note') or 'scanning…'}",
                         C_DIM))
            continue
        if p.get("err"):
            rows.append((f" {mark} {name} {p.get('err')}", C_BAD))
            continue
        pcts, text = _headline(p)
        if not pcts:
            tail = (text or {}).get("text") or p.get("note") or "—"
            color = C_BAD if sev_worst == "maxed" or "limit hit" in tail else C_DIM
            rows.append((f" {mark} {name} {tail}", color))
            continue
        r0 = pcts[0]
        color = C_BAD if _sev(r0) == "maxed" else \
            C_CLOCK if r0.get("clock") else _bar_color(r0["pct"])
        tail = r0["label"] + (" exhausted" if _sev(r0) == "maxed" else "")
        if r0.get("reset"):
            tail += f" · {r0['reset']}"
        # Secondary quotas: the most exhausted surfaces first, in its own colour.
        rest = sorted(pcts[1:], key=lambda r: _sev(r) == "maxed", reverse=True)
        for r in rest[:2]:
            s = f"{r['label']} {r['pct']:.0f}%"
            if _sev(r) == "maxed":
                tail += f" · {_rgb(C_BAD, 100)}{s} exhausted\033[0m{_rgb(color, 100)}"
            else:
                tail += f" · {s}"
        fill = C_BAD if _sev(r0) == "maxed" else brand
        rows.append((f" {mark} {name} {_bar(r0['pct'], 8, fill)} "
                     f"{r0['pct']:>3.0f}% {tail}", color))
    spark = _sparkline("burn")
    if spark:
        rows.append((f"   7d burn  {spark}", C_DIM))
    rows.append(("", C_DIM))
    rows.append((" j/k move · ⏎ detail · a all · r refresh · q", C_DIM))
    return rows


def build_detail(p: dict, spin: str = "◐") -> list[tuple[str, str]]:
    """All rows for one provider — the old dense section, scoped down."""
    brand = _BRAND.get(p["name"], C_NAME)
    name = _GLYPHS.get(p["name"], "·") + " " + p["name"]
    rows = [(f" {name} ", brand), ("", C_DIM)]
    if p.get("pending") or p.get("err"):
        note = f"{spin} {p.get('note') or 'scanning…'}" \
            if p.get("pending") else p.get("err") or "error"
        rows.append((f"   {note}", C_DIM if p.get("pending") else C_BAD))
        rows.append(("", C_DIM))
        rows.append((" h/← back · r refresh · q", C_DIM))
        return rows
    for r in p["rows"]:
        label = r["label"]
        if "pct" in r:
            sev = _sev(r)
            reset = f" · {r['reset']}" if r.get("reset") else ""
            word = " exhausted" if sev == "maxed" else ""
            color = C_BAD if sev == "maxed" else \
                C_CLOCK if r.get("clock") else _bar_color(r["pct"])
            fill = C_BAD if sev == "maxed" else brand
            rows.append((f"   {label:<7} {_bar(r['pct'], 12, fill)} "
                         f"{r['pct']:.0f}%{word}{reset}", color))
            rem = r.get("rem_s") or 0
            period = _PERIODS.get(label)
            if period and rem > 0:
                el = max(0.0, min(1.0, 1 - rem / period)) * 100
                rows.append((f"   {'win':<7} {_bar(el, 12, _ELAPSED)} {el:.0f}% elapsed", C_DIM))
        elif "stack" in r:
            rows.append((f"   {label:<7} {_stack_bar(r['stack'])} {r.get('text', '')}", C_TXT))
        else:
            hit = label == "cap" or "limit hit" in (r.get("text") or "")
            rows.append((f"   {label:<7} {r.get('text', '')}",
                         C_BAD if hit else C_TXT))
    if not p["rows"]:
        rows.append((f"   {p.get('note') or '—'}", C_DIM))
    if p.get("note") and p["rows"]:
        rows.append((f"   {p['note']}", C_DIM))
    chart = _week_chart(_SPARK_KEYS.get(p["name"], ""), brand)
    if chart:
        rows += chart
    else:
        spark = _sparkline("burn")
        if spark:
            rows.append((f"   7d      {spark}", C_DIM))
    rows.append(("", C_DIM))
    rows.append((" h/← back · r refresh · q", C_DIM))
    return rows


def build_all(data: dict, status: str = "", spin: str = "◐") -> list[tuple[str, str]]:
    """The classic dense dump — everything at once, one key away."""
    tag = f" · {status}" if status else ""
    rows = [(f" agent usage · all{tag}{_live_tag(data)} ", C_NAME), ("", C_DIM)]
    for p in data["providers"]:
        brand = _BRAND.get(p["name"], C_NAME)
        name = _pad(f"{_rgb(brand, 100)}{_GLYPHS.get(p['name'], '·')} {p['name']}\033[0m", 10)
        if p.get("pending"):
            rows.append((f"   {name} {spin} {p.get('note') or 'scanning…'}",
                         C_DIM))
            continue
        if p.get("err"):
            rows.append((f"   {name} {p.get('err')}", C_BAD))
            continue
        if not p["rows"]:
            rows.append((f"   {name} {p.get('note') or '—'}", C_DIM))
            continue
        for i, r in enumerate(p["rows"]):
            note = f" · {p['note']}" if i == 0 and p.get("note") else ""
            if "pct" in r:
                sev = _sev(r)
                reset = f" · {r['reset']}" if r.get("reset") else ""
                word = " exhausted" if sev == "maxed" else ""
                color = C_BAD if sev == "maxed" else \
                    C_CLOCK if r.get("clock") else _bar_color(r["pct"])
                fill = C_BAD if sev == "maxed" else brand
                rows.append((f"   {name} {r['label']} {_bar(r['pct'], 10, fill)} "
                             f"{r['pct']:.0f}%{word}{reset}{note}", color))
            elif "stack" in r:
                rows.append((f"   {name} {r['label']} {_stack_bar(r['stack'])} {r.get('text', '')}{note}", C_TXT))
            else:
                hit = r["label"] == "cap" or "limit hit" in (r.get("text") or "")
                rows.append((f"   {name} {r['label']} {r.get('text', '')}{note}",
                             C_BAD if hit else C_TXT))
    spark = _sparkline("burn")
    if spark:
        rows.append((f"   7d burn  {spark}", C_DIM))
    rows.append(("", C_DIM))
    rows.append((" a summary · r refresh · q", C_DIM))
    return rows


_last_box = [0, 0, 0, 0]  # top, left, w, h of the previous frame


def draw(rows: list[tuple[str, str]], p: int, cols: int, lines: int) -> None:
    pt, pl, pw, ph = _last_box
    out = []
    if ph:
        # erase the previous frame's footprint so smaller boxes leave no trail
        blank = " " * pw
        out += [f"\033[{pt + i};{pl}H{blank}" for i in range(ph)]
    if cols < 24 or lines < 6:
        # pane too small for the panel — a bare centered tag instead
        msg = " usage "
        top = max(lines // 2, 1)
        left = max((cols - len(msg)) // 2, 0)
        out.append(f"\033[{top};{left}H{_rgb(C_DIM, p)}{msg}")
        _last_box[:] = [top, left, len(msg), 1]
        sys.stdout.write("".join(out) + "\033[0m")
        sys.stdout.flush()
        return
    w = min(max(_vlen(t) for t, _ in rows) + 2, cols - 2)
    left = max((cols - w - 2) // 2, 0)
    n = min(len(rows), max(0, lines - 4))
    top = max((lines - n - 3) // 2, 0)
    b = _rgb(C_BORDER, p)
    out.append(f"\033[{top};{left}H{b}╭{'─' * w}╮")
    for i, (text, fg) in enumerate(rows[:n]):
        out.append(f"\033[{top + 1 + i};{left}H{b}│{_rgb(fg, p)}"
                   f"{_pad(_trunc(text, w), w)}{b}│")
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


def _status(loader: Loader, data: dict, spin: str) -> str:
    """Header tag while anything is in flight — '' once settled."""
    if not loader.alive():
        return ""
    n = len(loader.pending) + len(loader.live_pending)
    word = "loading" if not data.get("ts") else "refreshing"
    return f"{spin} {n} {word}"


def _respawn(loader: Loader, data: dict) -> Loader:
    """New loader for 'r'/auto-refresh: errored or empty providers go back
    to skeletons; populated rows stay visible while fresh data loads."""
    loader = Loader(loader.mods)
    for p in data["providers"]:
        if p.get("pending") or p.get("err") \
                or (not p["rows"] and p.get("note") in (None, "scanning…")):
            p.clear()
            p.update(_skeleton(p["name"]))
    loader.start(C.LIVE)
    return loader


def interactive() -> None:
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
        data, loader = _seed(C.LIVE, load_collectors())
        frame = 0
        # SIGWINCH → self-pipe so a resize redraws instantly instead of
        # waiting out the select timeout.
        winch_r, winch_w = os.pipe()
        os.set_blocking(winch_w, False)
        signal.set_wakeup_fd(winch_w)
        signal.signal(signal.SIGWINCH, lambda *_: None)
        for p_ in (20, 45, 70, 100):
            draw(build_summary(data, sel, _status(loader, data, _SPIN[0])),
                 p_, cols, lines)
            time.sleep(0.03)
        dirty_ts = 0.0
        while True:
            # 90ms tick only while something is loading — settles to 1s idle.
            tick = 0.09 if loader.alive() else 1.0
            r, _, _ = select.select([sys.stdin, winch_r], [], [], tick)
            cols, lines = os.get_terminal_size()
            if winch_r in r:
                try:
                    os.read(winch_r, 4096)
                except BlockingIOError:
                    pass
                r = [f for f in r if f != winch_r]
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
                elif k == "r" and not loader.alive():
                    loader = _respawn(loader, data)
            elif not loader.alive() and data.get("ts") \
                    and time.time() - data["ts"] > C.TTL \
                    and dirty_ts != data["ts"]:
                dirty_ts = data["ts"]
                loader = _respawn(loader, data)
            _drain(loader, data)
            if loader.alive():
                frame += 1
            spin = _SPIN[frame % len(_SPIN)]
            status = _status(loader, data, spin)
            rows = (build_summary(data, sel, status, spin) if mode == "summary"
                    else build_detail(data["providers"][sel], spin)
                    if mode == "detail" else build_all(data, status, spin))
            draw(rows, 100, cols, lines)
    finally:
        signal.set_wakeup_fd(-1)
        try:
            os.close(winch_r)
            os.close(winch_w)
        except OSError:
            pass
        termios.tcsetattr(fd, termios.TCSANOW, old)
        sys.stdout.write("\033[?25h\033[0m")


def main() -> None:
    if "--collect-only" in sys.argv:
        # quiet refresh for tab_bar's quota warning — no UI, no tty needed
        get_data(force=True)
        return
    if "--once" in sys.argv:
        for text, fg in build_all(get_data(force=False)):
            print(f"{_rgb(fg, 100)}{text}")
        print("\033[0m", end="")
        return
    sys.stdin = open("/dev/tty", "rb", buffering=0)
    interactive()


if __name__ == "__main__":
    main()
