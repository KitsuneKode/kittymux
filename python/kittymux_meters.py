"""kittymux_meters — one model for every provider's usage (pure: no kitty imports, no I/O except `load_history`).

A collector returns rows (`label`, `pct`, `reset`, `text`, …, and numeric sidecars `rem_s`, `window_s`, `tok`, `cached`, `sess`, `turns`, `ago_s`,
`state`). The panel does not draw rows, it draws METERS, of four kinds, so a new provider needs no UI code:

  quota    {kind, label, pct, rem_s, window_s, clock}      a gauge: used share, time to reset, the window it belongs to
  counter  {kind, label, value, unit, series, chips}       a number (and a week of it)
  state    {kind, label, text, tone}                       a chip; tone is calm | warm | hot | muted
  spend    {kind, label, amount, parts, text}              money, with the plan's share when the collector knows it

`meters()` reads the sidecars when a row has them and falls back to the row's label and text when it does not, so an old cache file written
before the sidecars existed still draws. Anything it cannot make sense of becomes a muted `state` meter with the text it was given
(cleaned), never a guess. Never raises, never returns a non-finite number."""
from __future__ import annotations

import json
import math
import os
import re
import time
from datetime import datetime, timedelta

import kittymux_place

PERIODS = {"5h": 5 * 3600, "day": 86400, "wk": 7 * 86400, "week": 7 * 86400, "mo": 30 * 86400}
HISTORY_KEYS = {"claude": "claude_fresh", "devin": "devin_tok"}      # provider -> the counter in agent-usage-history.json
LABEL_MAX = 12
_NOT_PLANS = {"not installed", "—", "no usage data", "collector error", "session totals · modified today"}
_UNITS = {"k": 1e3, "m": 1e6, "g": 1e9, "": 1.0}
_WAIT = re.compile(r"(?:(\d+)\s*d(?:ays?)?)?\s*(?:(\d+)\s*h(?:ours?)?)?\s*(?:(\d+)\s*m(?:in(?:ute)?s?)?)?\s*$")
_TOK = re.compile(r"([\d.]+)\s*([kKmMgG]?)\s*tok")
_CACHED = re.compile(r"\+\s*([\d.]+)\s*([kKmMgG]?)\s*cached")
_COUNT = re.compile(r"(\d+)\s*(sess|turns)")


def num(v) -> float | None:
    """A finite number or None (bools are not numbers here)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    f = float(v)
    return f if math.isfinite(f) else None


def parse_wait(text) -> float | None:
    """'resets in 3h 50m' / 'in 4d 19h' / 'in 9m' / 'in 42 minutes' / 'resets now' → seconds. None when it is not a wait."""
    if not isinstance(text, str):
        return None
    t = text.strip().lower()
    if t.endswith("now") and "in " not in t:
        return 0.0
    i = t.rfind("in ")
    if i < 0:
        return None
    m = _WAIT.fullmatch(t[i + 3:].strip())
    if not m or not any(m.groups()):
        return None
    d, h, mm = (int(x) if x else 0 for x in m.groups())
    return float(d * 86400 + h * 3600 + mm * 60)


def parse_ago(text) -> float | None:
    """'7d ago' / '3h ago' / '12m ago' → seconds."""
    m = re.search(r"(\d+)\s*([dhm])\s*ago", text) if isinstance(text, str) else None
    return float(int(m.group(1)) * {"d": 86400, "h": 3600, "m": 60}[m.group(2)]) if m else None


def _tokens(num_text: str, unit: str) -> float | None:
    try:
        return float(num_text) * _UNITS[unit.lower()]
    except (ValueError, KeyError):
        return None


def _label(raw) -> str:
    return kittymux_place.clean(str(raw if raw is not None else ""))[:LABEL_MAX]


def _clean(raw, limit: int = 60) -> str:
    return kittymux_place.clean(str(raw if raw is not None else ""))[:limit]


def quota(label: str, pct: float, rem_s=None, window_s=None, clock: bool = False) -> dict:
    return {"kind": "quota", "label": label, "pct": max(0.0, min(100.0, pct)), "rem_s": rem_s, "window_s": window_s, "clock": bool(clock)}


def state(label: str, text: str, tone: str = "muted") -> dict:
    return {"kind": "state", "label": label, "text": text, "tone": tone if tone in ("calm", "warm", "hot", "muted") else "muted"}


def _row_to_meters(row: dict) -> list[dict]:
    label = _label(row.get("label"))
    pct = num(row.get("pct"))
    text = _clean(row.get("text"))
    if pct is not None:
        rem = num(row.get("rem_s"))
        if rem is None:
            rem = parse_wait(row.get("reset"))
        window = num(row.get("window_s")) or PERIODS.get(label.lower())
        if label.lower() == "cap":                                    # Claude's cap: 100 % while it lasts, with the time it lasts
            return [state("cap", "limit hit", "hot")] + ([] if rem is None else [{"kind": "quota", "label": "cap", "pct": 100.0, "rem_s": max(0.0, rem), "window_s": None, "clock": False}])
        return [quota(label, pct, None if rem is None else max(0.0, rem), window, bool(row.get("clock")))]
    st = _clean(row.get("state"), 24)
    low = text.lower()
    tok = num(row.get("tok"))
    if tok is None:
        m = _TOK.search(text)
        tok = _tokens(*m.groups()) if m else None
    if tok is not None and low and ("tok" in low or row.get("tok") is not None):
        cached = num(row.get("cached"))
        if cached is None:
            cm = _CACHED.search(text)
            cached = _tokens(*cm.groups()) if cm else None
        counts = dict((u, int(n)) for n, u in _COUNT.findall(text))
        sess = num(row.get("sess"))
        sess = counts.get("sess") if sess is None else int(sess)
        turns = num(row.get("turns"))
        turns = counts.get("turns") if turns is None else int(turns)
        chips = []
        if sess:
            chips.append(f"{sess} sess")
        if turns:
            chips.append(f"{turns} turns")
        if cached:
            chips.append(f"+{_short(cached)} cache")
        return [{"kind": "counter", "label": label, "value": tok, "unit": "tok", "series": None, "chips": chips}]
    if label.lower() == "spend" or row.get("stack") is not None:
        stack = [v for v in (num(x) for x in (row.get("stack") or [])) if v is not None and v > 0] if isinstance(row.get("stack"), list) else []
        return [{"kind": "spend", "label": "spend", "amount": None, "parts": stack, "text": text}]
    if label.lower() == "today" and "lines" in low:
        m = re.search(r"(\d+)\s*lines", text)
        ai = re.search(r"(\d+)\s*%\s*AI", text)
        return [{"kind": "counter", "label": "today", "value": float(m.group(1)) if m else 0.0, "unit": "lines", "series": None,
                 "chips": [f"{ai.group(1)}% AI"] if ai else []}]
    if label.lower() == "plan" and "·" in text:
        plan, _, status = (x.strip() for x in text.partition("·"))
        return [state("plan", plan or "?", "muted"), state("status", status or "?", "calm" if status.lower() in ("active", "trialing") else "warm")]
    if low.startswith("window closed") or low == "idle" or st == "closed":
        return [state(label or "5h", "closed" if low != "idle" else "idle", "muted")]
    if label.lower() == "cap" or low.startswith("limit hit"):
        return [state("cap", ("hit " + text.split("hit", 1)[1].strip()) if "hit" in text else text, "warm")]
    if label.lower() in ("last",) and text:
        return [state("last", text, "muted")]
    if not text and not label:
        return []
    return [state(label or "info", text or "?", "muted")]


def _short(n: float) -> str:
    return f"{n / 1e9:.1f}G" if n >= 1e9 else f"{n / 1e6:.1f}M" if n >= 1e6 else f"{n / 1e3:.0f}k" if n >= 1e3 else str(int(n))


def week_series(history, key: str, today: datetime | None = None) -> list | None:
    """Seven daily values, oldest first, from agent-usage-history.json (`{day: {key: n}}`); None when there is nothing to draw."""
    if not isinstance(history, dict) or not key:
        return None
    today = today or datetime.fromtimestamp(time.time())
    out = []
    for back in range(6, -1, -1):
        day = (today - timedelta(days=back)).strftime("%Y-%m-%d")
        entry = history.get(day)
        out.append(num(entry.get(key)) if isinstance(entry, dict) else None)
    return out if any(v for v in out) else None


def load_history(state_dir: str) -> dict:
    try:
        with open(os.path.join(state_dir, "agent-usage-history.json")) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def meters(provider, history: dict | None = None, today: datetime | None = None) -> list[dict]:
    """Every meter a provider has, quotas first, then counters, states, spend. Never raises."""
    if not isinstance(provider, dict):
        return []
    out: list[dict] = []
    for row in provider.get("rows") if isinstance(provider.get("rows"), list) else []:
        if isinstance(row, dict):
            try:
                out += _row_to_meters(row)
            except Exception:
                continue
    name = str(provider.get("name") or "").lower()
    series = week_series(history, HISTORY_KEYS.get(name, ""), today)
    if series:
        for m in out:
            if m["kind"] == "counter" and m["unit"] == "tok":
                m["series"] = series
                break
    order = {"quota": 0, "counter": 1, "state": 2, "spend": 3}
    return sorted(out, key=lambda m: order.get(m["kind"], 9))      # sorted() is stable: the collector's order holds within a kind


def plan_of(provider) -> str:
    """A short plan name (codex's `plus`) from `note`; a sentence in `note` is a status, not a plan."""
    note = _clean(provider.get("note") if isinstance(provider, dict) else "", 20)
    return "" if not note or note.lower() in _NOT_PLANS or " " in note else note


def summary(provider) -> dict:
    """What the provider strip needs: `status` (ok | pending | error | missing | empty), the worst used share, and a tone."""
    if not isinstance(provider, dict):
        return {"name": "?", "status": "empty", "worst": None, "tone": "muted", "plan": ""}
    name = _clean(provider.get("name") or "provider", 20).lower()
    note = _clean(provider.get("note"), 40).lower()
    ms = meters(provider)
    status = ("pending" if provider.get("pending") else "error" if provider.get("err") or note == "collector error"
              else "missing" if note == "not installed" else "ok" if ms else "empty")
    shares = [m["pct"] for m in ms if m["kind"] == "quota" and not m.get("clock")]
    worst = max(shares) if shares else None
    if worst is not None:
        tone = "hot" if worst >= 100 else "warm" if worst >= 80 else "calm"
    elif any(m["kind"] == "state" and m["tone"] == "hot" for m in ms):
        tone = "hot"
    elif any(m["kind"] == "state" and m["tone"] == "warm" for m in ms):
        tone = "warm"
    else:
        tone = "calm" if status == "ok" else "muted"
    return {"name": name, "status": status, "worst": worst, "tone": tone, "plan": plan_of(provider)}


def worst_provider(providers) -> dict | None:
    """The summary of the provider closest to a wall (the strip's headline), None when nothing has a share."""
    best = None
    for p in providers if isinstance(providers, list) else []:
        s = summary(p)
        if s["worst"] is not None and (best is None or s["worst"] > best["worst"]):
            best = s
    return best
