"""The wait ledger (pure): how long agents waited on you, from the inbox's own times.

An agent that asks for you (a permission prompt or a question) is waiting from the moment its event FIRST appeared (`t0`) until you first looked at it (`ack_t`: you
focused its window, marked it read or dismissed it). While it is still unread it is waiting now. That is a measure of how quickly you got to each agent, not of how long
the agent's answer took, and it is only as complete as the inbox log (the newest 200 events).

One wait counts for at most CAP_S, so a night away does not swamp a day. Nothing here reads a file or the clock: `events` and `now` come from the caller."""
from __future__ import annotations

import math
from datetime import datetime, timedelta

NEEDS = ("permission", "question")
CAP_S = 3600.0            # one wait counts at most an hour toward a total
DAYS = 7


def _num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else None


def waits(events, now: float) -> list:
    """[{start, seconds, ongoing, agent, tab}] for every needs-you event with a measurable wait, oldest first."""
    out = []
    for ev in events if isinstance(events, list) else []:
        if not isinstance(ev, dict) or ev.get("kind") not in NEEDS:
            continue
        start = _num(ev.get("t0"))
        start = _num(ev.get("t")) if start is None else start
        if start is None or start > now:
            continue
        ongoing = ev.get("status") == "unread"
        end = now if ongoing else _num(ev.get("ack_t"))
        if end is None:
            continue                                            # read before the log kept when: nothing honest to say
        out.append({"start": start, "seconds": max(0.0, end - start), "ongoing": ongoing, "agent": str(ev.get("agent") or ""), "tab": str(ev.get("tab") or "")})
    return sorted(out, key=lambda w: w["start"])


def _median(values: list) -> float:
    s = sorted(values)
    n = len(s)
    return 0.0 if not n else s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def summary(events, now: float, today: datetime | None = None) -> dict | None:
    """None when the week holds no wait at all; else {today_s, week_s, count_today, count_week, median_s, longest_s, ongoing, series}."""
    today = today or datetime.fromtimestamp(now)
    days = [(today - timedelta(days=back)).date() for back in range(DAYS - 1, -1, -1)]
    series = [0.0] * DAYS
    counts = [0] * DAYS
    kept = []
    for w in waits(events, now):
        day = datetime.fromtimestamp(w["start"]).date()
        if day not in days:
            continue
        i = days.index(day)
        capped = min(w["seconds"], CAP_S)
        series[i] += capped
        counts[i] += 1
        kept.append((capped, w))
    if not kept:
        return None
    return {"today_s": series[-1], "week_s": sum(series), "count_today": counts[-1], "count_week": sum(counts),
            "median_s": _median([c for c, _w in kept]), "longest_s": max(w["seconds"] for _c, w in kept), "ongoing": sum(1 for _c, w in kept if w["ongoing"]),
            "series": series}


def fmt_dur(seconds) -> str:
    s = _num(seconds)
    if s is None:
        return ""
    if s < 60:
        return f"{int(s)}s"
    m = int(s // 60)
    h, mm = divmod(m, 60)
    return f"{h}h {mm}m" if h and mm else f"{h}h" if h else f"{m}m"


def format_text(summ: dict | None) -> str:
    """The plain-text answer for `kittymux inbox ledger`."""
    if not summ:
        return "nothing has waited on you in the last 7 days (the inbox keeps its newest 200 events)"
    line = (f"agents waited on you {fmt_dur(summ['today_s']) or '0s'} today over {summ['count_today']} wait{'s' if summ['count_today'] != 1 else ''}"
            f" · {fmt_dur(summ['week_s']) or '0s'} this week · median {fmt_dur(summ['median_s'])} · longest {fmt_dur(summ['longest_s'])}")
    if summ["ongoing"]:
        line += f" · {summ['ongoing']} waiting now"
    return line
