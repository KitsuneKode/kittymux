"""Theme-independent rows for the persistent panel's Usage view."""
import math
import time
import kittymux_place


def rows(data, columns, cells=len):
    from kittymux_deck import wrap_detail
    out = []
    def add(text, role="muted"):
        for line in wrap_detail(str(text), max(1, columns - 2), cells):
            out.append((" " + line, role))
    providers = data.get("providers") if isinstance(data, dict) else None
    if not isinstance(providers, list) or not providers:
        add("Usage", "text")
        add("Collecting local usage…")
        add("Live quotas are opt-in.")
        return out
    add("Provider limits", "text")
    stamp = data.get("ts", 0)
    age = max(0, int(time.time() - stamp)) if isinstance(stamp, (int, float)) and math.isfinite(stamp) else None
    add((f"Updated {age}s ago" if age is not None and stamp else "Snapshot age unavailable") + " · r refresh")
    if age is not None and stamp and age > 120:
        add("Stale snapshot · refreshing", "waiting")
    add("Live quotas are opt-in.")
    for p in providers:
        if not isinstance(p, dict):
            continue
        out.append(("", "muted"))
        add(kittymux_place.clean(str(p.get("name", "provider"))).title(), "text")
        if p.get("pending"):
            add("Collecting…")
            continue
        if p.get("err"):
            add(p["err"], "alert")
        for r in p.get("rows", []) if isinstance(p.get("rows"), list) else []:
            if not isinstance(r, dict):
                continue
            pct = r.get("pct")
            if isinstance(pct, (int, float)) and not isinstance(pct, bool) and math.isfinite(pct):
                role = "accent" if r.get("clock") else "alert" if pct >= 100 else "waiting" if pct >= 80 else "accent"
                add(f"{r.get('label', 'quota')}  {pct:.0f}%" + (" elapsed" if r.get("clock") else " used"), role)
                width = min(24, max(4, columns - 3))
                fill = round(max(0, min(100, pct)) / 100 * width)
                add("━" * fill + "─" * (width - fill), role)
                if r.get("reset"):
                    add(r["reset"])
            else:
                add(f"{r.get('label', '')}  {r.get('text', '')}")
        for key in ("note", "live_error"):
            if p.get(key):
                add(p[key])
    return out
