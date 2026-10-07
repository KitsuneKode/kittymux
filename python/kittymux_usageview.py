"""Theme-independent rows for the persistent panel's Usage view."""
from dataclasses import dataclass
from datetime import date, timedelta

import math
import re
import time
import kittymux_place

def rows(data, columns, cells=len):
    from kittymux_deck import wrap_detail
    out = []

    def add(text, role='muted'):
        for line in wrap_detail(str(text), max(1, columns - 2), cells):
            out.append((' ' + line, role))
    providers = data.get('providers') if isinstance(data, dict) else None
    if not isinstance(providers, list) or not providers:
        add('Usage', 'text')
        add('Collecting local usage…')
        add('Live quotas are opt-in.')
        return out
    add('Provider limits', 'text')
    stamp = data.get('ts', 0)
    age = max(0, int(time.time() - stamp)) if isinstance(stamp, (int, float)) and math.isfinite(stamp) else None
    add((f'Updated {age}s ago' if age is not None and stamp else 'Snapshot age unavailable') + ' · r refresh')
    if age is not None and stamp and (age > 120):
        add('Stale snapshot · refreshing', 'waiting')
    add('Live quotas are opt-in.')
    for p in providers:
        if not isinstance(p, dict):
            continue
        out.append(('', 'muted'))
        add(kittymux_place.clean(str(p.get('name', 'provider'))).title(), 'text')
        if p.get('pending'):
            add('Collecting…')
            continue
        if p.get('err'):
            add(p['err'], 'alert')
        for r in p.get('rows', []) if isinstance(p.get('rows'), list) else []:
            if not isinstance(r, dict):
                continue
            pct = r.get('pct')
            if isinstance(pct, (int, float)) and (not isinstance(pct, bool)) and math.isfinite(pct):
                role = 'accent' if r.get('clock') else 'alert' if pct >= 100 else 'waiting' if pct >= 80 else 'accent'
                add(f"{r.get('label', 'quota')}  {pct:.0f}%" + (' elapsed' if r.get('clock') else ' used'), role)
                width = min(24, max(4, columns - 3))
                fill = round(max(0, min(100, pct)) / 100 * width)
                add('━' * fill + '─' * (width - fill), role)
                if r.get('reset'):
                    add(r['reset'])
            else:
                add(f"{r.get('label', '')}  {r.get('text', '')}")
        for key in ('note', 'live_error'):
            if p.get(key):
                add(p[key])
    return out

@dataclass(frozen=True)
class Line:
    runs: tuple
    surface: bool = False

def words(text, width, cells=len):
    """Wrap prose at words; preserve complete numeric groups when they fit."""
    text = kittymux_place.clean(text)
    width = max(1, width)
    out = []
    line = ''
    tokens = text.split()
    groups = []
    i = 0
    while i < len(tokens):
        word = tokens[i]
        if re.fullmatch('\\d+(?:\\.\\d+)?[kMGT]?', word) and i + 1 < len(tokens) and (tokens[i + 1] in ('sessions', 'session', 'sess', 'tokens', 'tok')):
            word += ' ' + tokens[i + 1]
            i += 1
        groups.append(word)
        i += 1
    for word in groups:
        if line and cells(line + ' ' + word) > width:
            out.append(line)
            line = ''
        while cells(word) > width:
            piece = ''
            for ch in word:
                if cells(piece + ch) > width:
                    break
                piece += ch
            if not piece:
                word = word[1:]
                continue
            out.append(piece)
            word = word[len(piece):]
        if word:
            line = (line + ' ' + word).strip()
    if line:
        out.append(line)
    return out

def compact(value):
    for scale, suffix in ((1000000000.0, 'G'), (1000000.0, 'M'), (1000.0, 'k')):
        if value >= scale:
            return f'{value / scale:.1f}{suffix}'
    return str(int(value))

def activity(history, provider, width, today=None):
    """Seven calendar days of exact v2 counters; gaps mean unrecorded, not zero."""
    key = {'claude': 'claude_fresh'}.get(provider)
    if not key or not isinstance(history, dict):
        return []
    today = today or date.today()
    vals = []
    for i in range(6, -1, -1):
        item = history.get((today - timedelta(days=i)).isoformat(), {})
        v = item.get(key) if isinstance(item, dict) and item.get('_daily_version') == 2 else None
        vals.append(v if isinstance(v, (int, float)) and (not isinstance(v, bool)) and math.isfinite(v) and (v >= 0) else None)
    known = [v for v in vals if v is not None]
    if not known:
        return []
    peak = max(known) or 1
    blocks = '▁▂▃▄▅▆▇█'
    gap = ' ' if width >= 13 else ''
    graph = gap.join(('·' if v is None else blocks[min(7, round(v / peak * 7))] for v in vals))
    return [(graph, 'accent'), (f'7d tokens · peak {compact(max(known))}', 'muted'), ('· unrecorded · today partial', 'muted')]

def dashboard(data, columns, cells=len, history=None, trends=None, details=False, now=None):
    columns = max(1, columns)
    room = max(1, columns - 4)
    out = []
    omitted = False

    def add(text, role='muted', surface=False):
        nonlocal omitted
        raw = str(text)
        if len(raw) > 1024:
            omitted = True
        for chunk in words(raw[:1024], room, cells):
            if len(out) >= 512:
                omitted = True
                break
            out.append(Line((('  ' + chunk, role),), surface))
    providers = data.get('providers') if isinstance(data, dict) else None
    if not isinstance(providers, list) or not providers:
        add('Collecting usage…', 'text')
        add('Press r to refresh.')
        return out
    stamp = data.get('ts', 0)
    now = time.time() if now is None else now
    age = max(0, int(now - stamp)) if isinstance(stamp, (int, float)) and (not isinstance(stamp, bool)) and math.isfinite(stamp) and stamp else None
    live = data.get('live')
    has_live = isinstance(live, dict) and any((isinstance(v, dict) and v.get('rows') for v in live.values()))
    add(('Local refresh' if has_live else 'Local snapshots') + ' · ' + (f'{age}s ago' if age is not None else 'age unknown'))
    if age is not None and age > 120:
        add('Stale · r refresh', 'waiting')
    for p in providers[:16]:
        if len(out) >= 510:
            omitted = True
            break
        if not isinstance(p, dict):
            continue
        out.append(Line((('', 'muted'),)))
        name = kittymux_place.clean(str(p.get('name', 'provider')))[:24]
        label = name.title()
        edge = '─' * max(0, room - cells(label) - 1)
        out.append(Line(((' ▎', 'accent'), (label, 'text'), (' ' + edge, 'track')), True))
        if p.get('pending'):
            add('Collecting…', 'muted', True)
            continue
        if p.get('err'):
            add(p['err'], 'alert', True)
            add('r retry', 'muted', True)
        live_provider = live.get(name) if isinstance(live, dict) else None
        if isinstance(live_provider, dict) and live_provider.get('rows'):
            live_ts = live_provider.get('ts')
            if isinstance(live_ts, (int, float)) and not isinstance(live_ts, bool) and math.isfinite(live_ts) and live_ts > 0:
                live_age = max(0, int(now - live_ts))
                add(('Live stale' if live_age > 300 else 'Live snapshot') + f' · {live_age}s ago', 'waiting' if live_age > 300 else 'muted', True)
            else:
                add('Live age unknown', 'waiting', True)
        if p.get('live_error'):
            add(p['live_error'], 'waiting', True)
        elif isinstance(live_provider, dict) and live_provider.get('error'):
            add('Live unavailable · r retry', 'waiting', True)
        provider_rows = p.get('rows', [])[:64] if isinstance(p.get('rows'), list) else []
        if not provider_rows and not p.get('err'):
            add(p.get('note') or 'No usage data · r refresh', 'muted', True)
        for r in provider_rows:
            if len(out) >= 509:
                omitted = True
                break
            if not isinstance(r, dict):
                continue
            pct = r.get('pct')
            quota = isinstance(pct, (int, float)) and (not isinstance(pct, bool)) and math.isfinite(pct)
            if quota:
                role = 'accent' if r.get('clock') else 'alert' if pct >= 100 else 'waiting' if pct >= 80 else 'accent'
                value = f'{pct:.0f}% elapsed' if r.get('clock') else f'{max(0, 100 - pct):.0f}% left'
                label = kittymux_place.clean(str(r.get('label', 'quota')))[:24]
                if cells(label + ' ' + value) <= room:
                    out.append(Line((('  ' + label + ' ' * max(1, room - cells(label) - cells(value)), 'text'), (value, role)), True))
                else:
                    add(label, 'text', True)
                    add(value, role, True)
                width = max(1, room)
                fill = round(min(100, max(0, pct)) * width / 100)
                out.append(Line((('  ', 'muted'), ('━' * fill, role), ('─' * (width - fill), 'track')), True))
                if not r.get('clock'):
                    add(f'{pct:.0f}% used', 'muted', True)
                if r.get('reset'):
                    add(r['reset'], 'muted', True)
            else:
                add(str(r.get('label', '')) + ' ' + str(r.get('text', '')), 'text', True)
        for text, role in activity(history or {}, name, room):
            add(text, role, True)
        series = (trends or {}).get(name, []) if isinstance(trends, dict) else []
        if series:
            for text, role in series:
                add(text, role, True)
        elif any((isinstance(r, dict) and isinstance(r.get('pct'), (int, float)) for r in provider_rows)):
            add('No trend yet · collecting', 'muted', True)
        if details:
            if p.get('note') and provider_rows:
                add(p['note'], 'muted', True)
    if details:
        add('Live quotas: KITTYMUX_USAGE_LIVE=1')
    if omitted:
        out = out[:512]
        out.append(Line((('  Detail omitted', 'waiting'),)))
    return out

def trend_lines(data, width, now=None):
    """48 hourly quota samples, fixed 0–100% scale. Missing hours retain gaps."""
    now = time.time() if now is None else now
    samples = data.get('samples', []) if isinstance(data, dict) else []
    if not isinstance(samples, list):
        return {}
    series = {}
    end = int(now // 3600) * 3600
    for s in samples[-2048:]:
        if not isinstance(s, dict):
            continue
        p, r, t, v = (s.get('provider'), s.get('row'), s.get('at'), s.get('pct'))
        if p not in ('claude', 'codex', 'cursor', 'devin') or not isinstance(r, int) or isinstance(r, bool) or not 0 <= r < 16:
            continue
        if not all((isinstance(n, (int, float)) and (not isinstance(n, bool)) and math.isfinite(n) for n in (t, v))):
            continue
        if not 0 <= v <= 100 or not end - 47 * 3600 <= t <= end:
            continue
        series.setdefault(p, {}).setdefault(r, {})[int(t // 3600) * 3600] = v
    out = {}
    blocks = '▁▂▃▄▅▆▇█'
    for p, row_points in series.items():
        points = row_points[min(row_points)]
        if len(points) < 2:
            continue
        n = min(48, max(2, width))
        values = []
        for i in range(n):
            a = end - (48 - i * 48 // n) * 3600 + 3600
            b = end - (48 - (i + 1) * 48 // n) * 3600 + 3600
            group = [(t, v) for t, v in points.items() if a <= t < b]
            values.append('·' if not group else blocks[min(7, round(max(group)[1] * 7 / 100))])
        captions = [('48h quota', 'muted'), ('0–100% · gap', 'muted')] if width < 16 else [('48h · first quota · 0–100%', 'muted'), ('· no recorded sample', 'muted')]
        out[p] = [(''.join(values), 'accent'), *captions]
    return out
