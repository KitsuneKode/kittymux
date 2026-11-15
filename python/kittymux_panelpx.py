"""Pure pixel Usage and Inbox views, sharing the deck's live theme and resources.

Coordinates and scroll are image pixels. Content bounds start at zero beneath
HEADER_END; hits are clipped to the visible image and never overlap. No provider
fetch, acknowledgement, focus change, animation or retained window state lives here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import time

import kittymux_deckpx as D
import kittymux_inboxview as I
import kittymux_meters as M
import kittymux_place
import kittymux_theme as th
import kittymux_usageview as V

HEADER_END = 104.0
FOOTER_H = 32.0
MAX_PROVIDERS = 64
MESSAGE_MAX = 4096
PAD = 10.0


@dataclass
class Rendered:
    surface: object
    hits: list
    content_height: float
    selected_bounds: tuple | None


def _clean(value, limit=240):
    return kittymux_place.clean(str(value if value is not None else '')[:limit])


def _number(value, default=0):
    n = M.num(value)
    return default if n is None else n


def _ink(pt, color=None):
    return th.ensure_contrast(pt.p.text if color is None else color, pt.p.card, 4.5)


def _text(pt, x, cy, text, size=12, color=None, width=None, bold=False):
    return pt.text(x, cy, _clean(text, MESSAGE_MAX), size, _ink(pt, color), width=width,
                   weight=D.Pango.Weight.SEMIBOLD if bold else D.Pango.Weight.NORMAL)


def _paragraph(pt, text, width, size=12):
    """A private copy: wrapping must not mutate a shared cached one-line layout."""
    lo = pt.layout(_clean(text, MESSAGE_MAX), size, width=max(1, width)).copy()
    lo.set_ellipsize(D.Pango.EllipsizeMode.NONE)
    lo.set_wrap(D.Pango.WrapMode.WORD_CHAR)
    _ink_rect, logical = lo.get_pixel_extents()
    return lo, logical.height


def _draw_paragraph(pt, lo, x, y, color=None):
    pt.cr.set_source_rgba(*D.rgb(_ink(pt, color)))
    pt.cr.move_to(x, y)
    D.PangoCairo.show_layout(pt.cr, lo)


def _hit(hits, kind, value, x, y, w, h, width, top, bottom):
    left, right = max(0, x), min(width, x + w)
    a, b = max(top, y), min(bottom, y + h)
    if right > left and b > a:
        hits.append((kind, value, left, a, right - left, b - a))


def _button(pt, hits, kind, value, label, x, y, w, h, width, top, bottom, active=False):
    pt.surface(x, y, w, h, min(10, h / 2), .11 if active else .045, rim=.10 if active else .05)
    _text(pt, x + 8, y + h / 2, label, 11, width=max(1, w - 16), bold=active)
    _hit(hits, kind, value, x, y, w, h, width, top, bottom)


def _start(palette, width, height, resources):
    width, height = max(1, int(width)), max(1, int(height))
    surf = D.cairo.ImageSurface(D.cairo.FORMAT_ARGB32, width, height)
    cr = D.cairo.Context(surf)
    cr.set_source_rgba(*D.rgb(palette.bar))
    cr.paint()
    return surf, D.Painter(cr, 1, palette, resources=resources), width, height, []


def _header(pt, title, subtitle, width, warning=False):
    _text(pt, PAD, 21, title, 17, width=max(1, width - PAD * 2), bold=True)
    _text(pt, PAD, 40, subtitle, 10, pt.p.waiting if warning else pt.p.muted,
          width=max(1, width - PAD * 2))


def _footer(pt, hits, keys, width, height):
    top = max(0, height - FOOTER_H)
    pt.cr.set_source_rgba(*D.rgb(pt.p.bar))
    pt.cr.rectangle(0, top, width, FOOTER_H)
    pt.cr.fill()
    x = PAD
    for token, label in keys:
        w = max(28, pt.text_w(label, 11) + 20)
        if x + w > width - PAD:
            break
        _button(pt, hits, 'key', token, label, x, top + 4, w, 24, width, top, height)
        x += w + 5


def _body(pt, height, scroll, content_height):
    bottom = max(HEADER_END, height - FOOTER_H)
    room = max(0, height - FOOTER_H - HEADER_END)
    offset = max(0, min(_number(scroll), max(0, content_height - room)))
    pt.cr.save()
    pt.cr.rectangle(0, min(height, HEADER_END), pt.cr.get_target().get_width(), room)
    pt.cr.clip()
    pt.cr.translate(0, HEADER_END - offset)
    return offset, min(height - FOOTER_H, bottom)


def _body_hit(hits, kind, value, x, y, w, h, width, height, scroll):
    _hit(hits, kind, value, x, HEADER_END + y - scroll, w, h,
         width, HEADER_END, max(0, height - FOOTER_H))


def _freshness(data, provider, now):
    out = []
    if provider.get('sample_age_unknown'):
        out.append(('account sample age unknown', True))
    sample = M.num(provider.get('sample_ts'))
    if sample is not None and sample > 0:
        age = max(0, now - sample)
        out.append(('sample just now' if age < 60 else 'sample ' + V.fmt_span(age) + ' ago', age >= V.SAMPLE_STALE_S))
    name = _clean(provider.get('name'), 80).lower()
    live = data.get('live') if isinstance(data.get('live'), dict) else {}
    entry = live.get(name)
    if isinstance(entry, dict) and entry.get('rows'):
        ts = M.num(entry.get('ts'))
        age = max(0, now - ts) if ts is not None and ts > 0 else None
        out.append(('live · age unknown', True) if age is None else
                   ('live ' + ('stale ' if age > V.LIVE_STALE_S else '') + V.fmt_span(age) + ' ago', age > V.LIVE_STALE_S))
    err = provider.get('live_error')
    if err:
        out.append((_clean(err, 240), True))
    elif isinstance(entry, dict) and entry.get('error'):
        out.append(('live unavailable · R retry', True))
    if not out:
        ts = M.num(data.get('ts'))
        age = max(0, now - ts) if ts is not None and ts > 0 else None
        out.append(('cache · age unknown', True) if age is None else
                   ('cache just now' if age < 60 else 'cache ' + ('stale ' if age > V.STALE_S else '') + V.fmt_span(age) + ' ago', age > V.STALE_S))
    return out


def _provider_strip(pt, hits, providers, selected, width, height):
    per = max(1, int((width - PAD * 2 + 5) // 78))
    cap = per * 2
    start = max(0, min(selected - cap // 2, len(providers) - cap))
    shown = list(range(start, min(len(providers), start + cap)))
    w = max(1, (width - PAD * 2 - (per - 1) * 5) / per)
    for position, i in enumerate(shown):
        x, y = PAD + (position % per) * (w + 5), 50 + (position // per) * 26
        name = _clean(providers[i].get('name') or 'Provider', 80).title()
        _button(pt, hits, 'provider', i, name, x, y, w, 22,
                width, 0, min(height - FOOTER_H, HEADER_END), i == selected)


def _usage_blocks(pt, provider, data, history, now, details, inner):
    blocks = []
    summary = M.summary(provider)
    status = summary['status']
    if status != 'ok':
        message = ('Collecting usage…' if status == 'pending' else
                   _clean(provider.get('err') or 'Usage unavailable', 240) if status == 'error' else
                   'Not installed' if status == 'missing' else 'No usage data yet')
        lo, h = _paragraph(pt, message, inner)
        blocks.append(('message', lo, h + 12, pt.p.alert if status == 'error' else pt.p.muted))
    elif isinstance(provider.get('accounts'), list) and provider['accounts']:
        groups, exhausted, partial = {}, 0, False
        accounts = [a for a in provider['accounts'][:16] if isinstance(a, dict)]
        for account in accounts:
            label = _clean(account.get('label') or 'Account', 80)
            meters = M.meters(account)
            quotas = [m for m in meters if m['kind'] == 'quota' and not m.get('clock')]
            exhausted += bool(quotas) and all(m['pct'] >= 100 for m in quotas)
            partial = partial or any(m['pct'] >= 100 for m in quotas)
            for meter in meters:
                if meter['kind'] == 'quota' and not meter.get('clock'):
                    groups.setdefault(meter['label'] or 'Quota', []).append((label, meter))
                elif meter['kind'] == 'state':
                    lo, h = _paragraph(pt, label + ' · ' + meter['text'], inner, 11)
                    blocks.append(('message', lo, h + 12, pt.p.muted))
        if exhausted:
            lo, h = _paragraph(pt, f'{exhausted} of {len(accounts)} accounts out', inner, 11)
            blocks.insert(0, ('message', lo, h + 12, pt.p.waiting))
        elif partial:
            lo, h = _paragraph(pt, 'Some quota windows are at a limit', inner, 11)
            blocks.insert(0, ('message', lo, h + 12, pt.p.waiting))
        per = max(1, int((inner + 8) // 105))
        for label, members in groups.items():
            blocks.append(('accounts', (label, members), 24 + ((len(members) + per - 1) // per) * 82, None))
        if details:
            for account in accounts:
                lo, h = _paragraph(pt, _clean(account.get('label')) + (' · ' + _clean(account.get('plan')) if account.get('plan') else ''), inner, 11)
                blocks.append(('message', lo, h + 12, pt.p.muted))
    else:
        today = datetime.fromtimestamp(now)
        for meter in M.meters(provider, history, today):
            kind = meter['kind']
            if kind == 'quota':
                blocks.append((kind, meter, 90, None))
            elif kind == 'counter':
                blocks.append((kind, meter, 91 if meter.get('series') else 67, None))
            else:
                message = (f"{meter['label']} · {meter['text']}" if kind == 'state' else meter.get('text', ''))
                if message:
                    lo, h = _paragraph(pt, message, inner, 11)
                    color = {'hot': pt.p.alert, 'warm': pt.p.waiting}.get(meter.get('tone'), pt.p.muted)
                    blocks.append(('message', lo, h + 12, color))
    for message, warning in _freshness(data, provider, now):
        lo, h = _paragraph(pt, message, inner, 10)
        blocks.append(('message', lo, h + 9, pt.p.waiting if warning else pt.p.muted))
    if details:
        note = _clean(provider.get('note'), 1024)
        if note:
            lo, h = _paragraph(pt, note, inner, 11)
            blocks.append(('message', lo, h + 12, pt.p.muted))
        if not data.get('live'):
            lo, h = _paragraph(pt, 'Local data · live quotas are opt-in. KITTYMUX_USAGE_LIVE=1', inner, 10)
            blocks.append(('message', lo, h + 12, pt.p.faint))
    return blocks


def _draw_accounts(pt, payload, x, y, inner):
    label, members = payload
    _text(pt, x, y + 7, label, 12, width=inner, bold=True)
    per = max(1, int((inner + 8) // 105))
    segment_w = (inner - (per - 1) * 8) / per
    for i, (account, meter) in enumerate(members):
        bx, by = x + i % per * (segment_w + 8), y + 24 + i // per * 82
        left = max(0, 100 - meter['pct'])
        color = pt.p.alert if left <= 0 else pt.p.waiting if left <= 20 else pt.p.done
        _text(pt, bx, by + 6, account, 10, pt.p.muted, width=segment_w)
        _text(pt, bx, by + 27, f'{round(left)}% left', 17, color, width=segment_w, bold=True)
        pt.fill_rrect(bx, by + 43, segment_w, 6, 3, pt.p.track)
        if left:
            pt.fill_rrect(bx, by + 43, segment_w * left / 100, 6, 3, _ink(pt, color))
        pace = V._pace(meter)
        if pace is not None:
            pt.cr.set_source_rgba(*D.rgb(_ink(pt, pt.p.muted)))
            pt.cr.rectangle(bx + min(segment_w - 1, segment_w * (1 - pace / 100)), by + 41, 1, 10)
            pt.cr.fill()
        rem = M.num(meter.get('rem_s'))
        _text(pt, bx, by + 63, 'reset unknown' if rem is None else 'resets ' + V.fmt_span(rem), 10, pt.p.muted, width=segment_w)


def _draw_quota(pt, meter, x, y, inner):
    clock = meter.get('clock')
    remaining = 100 - meter['pct']
    value = f"{round(meter['pct'] if clock else remaining)}%"
    label = 'of window' if clock else 'remaining'
    color = pt.p.muted if clock else pt.p.alert if remaining <= 0 else pt.p.waiting if remaining <= 20 else pt.p.done
    _text(pt, x, y + 8, meter['label'] or 'quota', 11, pt.p.muted, width=inner)
    number_w = _text(pt, x, y + 33, value, 27, color, width=inner, bold=True)
    if number_w + 8 < inner:
        _text(pt, x + number_w + 8, y + 37, label, 10, pt.p.muted, width=inner - number_w - 8)
    pt.fill_rrect(x, y + 53, inner, 5, 2.5, pt.p.track)
    share = meter['pct'] if clock else remaining
    if share > 0:
        pt.fill_rrect(x, y + 53, inner * share / 100, 5, 2.5, _ink(pt, color))
    pace = V._pace(meter)
    if pace is not None:
        tick = x + inner * (1 - pace / 100)
        pt.cr.set_source_rgba(*D.rgb(_ink(pt, pt.p.muted)))
        pt.cr.rectangle(min(x + inner - 1, tick), y + 51, 1, 9)
        pt.cr.fill()
    rem = M.num(meter.get('rem_s'))
    caption = 'reset unknown' if rem is None else 'resets ' + V.fmt_span(rem)
    if pace is not None:
        caption += ' · ' + ('under pace' if meter['pct'] <= pace else 'over pace')
    _text(pt, x, y + 74, caption, 10, pt.p.muted, width=inner)


def _draw_counter(pt, meter, x, y, inner):
    _text(pt, x, y + 8, meter['label'] or 'counter', 11, pt.p.muted, width=inner)
    _text(pt, x, y + 34, V.fmt_amount(meter['value'], meter['unit']) + ' ' + _clean(meter['unit']),
          24, width=inner, bold=True)
    chips = ' · '.join(_clean(c, 80) for c in (meter.get('chips') or [])[:8])
    _text(pt, x, y + 56, chips or 'measured total', 10, pt.p.muted, width=inner)
    series = meter.get('series')
    if series:
        peak = max((v for v in series if M.num(v) is not None), default=0) or 1
        gap, w = 4, max(1, (inner - 6 * 4) / 7)
        for i, value in enumerate(series[:7]):
            h = max(1, 19 * max(0, _number(value)) / peak)
            pt.fill_rrect(x + i * (w + gap), y + 82 - h, w, h, 2, pt.p.muted if value is None else pt.p.accent, .35 if value is None else .65)


def usage(data, history, selected, palette, width, height, *, now=None, details=False, scroll=0, hover=None, resources=None):
    """Selected provider's normalized meters; percentages always say remaining.

    A clock meter keeps its original meaning; counters and unknown values never
    receive a fabricated quota. `selected` and provider hits use provider indexes.
    """
    now = time.time() if now is None else _number(now)
    data = data if isinstance(data, dict) else {}
    raw = data.get('providers')
    providers = [p for p in raw[:MAX_PROVIDERS] if isinstance(p, dict)] if isinstance(raw, list) else []
    selected = max(0, min(int(_number(selected)), max(0, len(providers) - 1)))
    surf, pt, width, height, hits = _start(palette, width, height, resources)
    inner = max(1, width - 4 * PAD)
    ts = M.num(data.get('ts'))
    age = max(0, now - ts) if ts is not None and ts > 0 else None
    subtitle = f"{len(providers)} provider{'s' if len(providers) != 1 else ''}"
    if age is not None and age > V.STALE_S:
        subtitle += ' · cache stale ' + V.fmt_span(age)
    _header(pt, 'Usage', subtitle, width, age is not None and age > V.STALE_S)
    _provider_strip(pt, hits, providers, selected, width, height)
    provider = providers[selected] if providers else {}
    blocks = _usage_blocks(pt, provider, data, history, now, details, inner) if providers else []
    if not providers:
        lo, h = _paragraph(pt, 'Collecting local usage…', inner)
        blocks = [('message', lo, h + 12, pt.p.muted)]
    card_h = 54 + sum(b[2] for b in blocks)
    content_height = card_h + PAD * 2
    offset, _ = _body(pt, height, scroll, content_height)
    pt.surface(PAD, PAD, max(1, width - PAD * 2), card_h, 14, .035, rim=.08)
    name = _clean(provider.get('name') or 'Local usage', 80)
    icon = name.lower()
    has_icon = pt.icon(icon, PAD * 2, PAD + 15, 18, _ink(pt, pt.p.muted)) if icon in ('codex', 'claude', 'cursor', 'devin') else False
    _text(pt, PAD * 2 + (26 if has_icon else 0), PAD + 24, name.title(), 15,
          width=max(1, inner - (26 if has_icon else 0)), bold=True)
    y = PAD + 49
    for kind, payload, block_h, color in blocks:
        if kind == 'quota':
            _draw_quota(pt, payload, PAD * 2, y, inner)
        elif kind == 'accounts':
            _draw_accounts(pt, payload, PAD * 2, y, inner)
        elif kind == 'counter':
            _draw_counter(pt, payload, PAD * 2, y, inner)
        else:
            _draw_paragraph(pt, payload, PAD * 2, y, color)
        y += block_h
    pt.cr.restore()
    _footer(pt, hits, [('D', 'D details'), ('R', 'R refresh'), ('?', '?')], width, height)
    surf.flush()
    return Rendered(surf, hits, content_height, (PAD, PAD + card_h) if providers else None)


def _event_identity(event):
    return event.get('id') if isinstance(event.get('id'), str) else ''


def inbox(events, filter, selected, palette, width, height, *, now=None, expanded=None, scroll=0, hover=None, undo=False, resources=None):
    """Compact event summaries with deliberate expansion, keyed by event ID.

    Selection accepts an event ID (preferred) or a visible-list index. Expansion
    accepts one ID or a collection of IDs. Jump/Dismiss exist on expanded cards;
    expansion itself never reads, dismisses or focuses an event.
    """
    now = time.time() if now is None else _number(now)
    events = events if isinstance(events, list) else []
    filter = filter if filter in dict(I.FILTERS) else 'all'
    items = I.visible(events, filter, now)
    if M.num(selected) is not None:
        index = max(0, min(int(selected), max(0, len(items) - 1)))
        selected = _event_identity(items[index]) if items else None
    opened = {expanded} if isinstance(expanded, str) else set(expanded) if isinstance(expanded, (list, tuple, set, frozenset)) else set()
    surf, pt, width, height, hits = _start(palette, width, height, resources)
    _header(pt, 'Inbox', f'{I.unread(events)} unread · {I.needs_you(events)} need you', width)
    tally = I.counts(events, now)
    full = [label + (f' {tally[key]}' if tally[key] else '') for key, label in I.FILTERS]
    if sum(pt.text_w(t, 11) + 16 for t in full) + 15 > width - PAD * 2:
        full = ['All', 'Needs', 'Done', 'Limits']
    per = max(1, (width - PAD * 2 - 15) / 4)
    x = PAD
    for (key, _label), label in zip(I.FILTERS, full):
        _button(pt, hits, 'filter', key, label, x, 66, per, 26, width, 0,
                min(HEADER_END, height - FOOTER_H), key == filter)
        x += per + 5
    inner = max(1, width - PAD * 4)
    cards, y, selected_bounds = [], PAD, None
    for event in items:
        id = _event_identity(event)
        is_open = id in opened
        title = _clean(event.get('title') or event.get('body') or 'No message', MESSAGE_MAX)
        if is_open:
            summary, summary_h = _paragraph(pt, title, inner, 12)
        else:
            summary = pt.layout(title, 12, width=inner)
            summary_h = summary.get_pixel_extents()[1].height
        body = _clean(event.get('body'), MESSAGE_MAX)
        body_layout, body_h = (None, 0)
        if is_open and body and body != title:
            body_layout, body_h = _paragraph(pt, body, inner, 12)
        reset = M.num(event.get('reset_at')) if event.get('kind') == 'limit' else None
        detail_h = (body_h + 16 if body_layout is not None else 0) + (24 if reset is not None else 0)
        card_h = 42 + summary_h + detail_h + (45 if is_open else 12)
        cards.append((event, id, y, card_h, summary, summary_h, body_layout, body_h, reset, is_open))
        if id == selected:
            selected_bounds = (y, y + card_h)
        y += card_h + 8
    content_height = y if cards else 110
    offset, _ = _body(pt, height, scroll, content_height)
    if not cards:
        pt.surface(PAD, PAD, max(1, width - PAD * 2), 86, 14, .035, rim=.08)
        _text(pt, PAD * 2, 37, 'All clear', 16, width=inner, bold=True)
        _text(pt, PAD * 2, 63, 'Nothing in this filter' if filter != 'all' else 'Nothing waits on you', 11, pt.p.muted, width=inner)
    for event, id, y, card_h, summary, summary_h, body, body_h, reset, is_open in cards:
        if HEADER_END + y + card_h - offset <= HEADER_END or HEADER_END + y - offset >= height - FOOTER_H:
            continue
        is_selected = id == selected
        hot = hover == ('select', id) or hover == ('expand', id)
        pt.surface(PAD, y, max(1, width - PAD * 2), card_h, 13, .085 if is_selected else .055 if hot else .03, rim=.11 if is_selected else .06)
        kind = event.get('kind')
        color = pt.p.waiting if kind in ('permission', 'question') else pt.p.alert if kind in ('error', 'limit') else pt.p.done if kind == 'done' else pt.p.muted
        glyph = I.KIND.get(kind, ('·', 'muted'))[0]
        _text(pt, PAD * 2, y + 19, glyph, 13, color, width=14, bold=True)
        agent = _clean(event.get('agent') or 'Agent', 80).title()
        tab = _clean(event.get('tab'), 100)
        identity = agent + (' · ' + tab if tab and tab.lower() != agent.lower() else '')
        count = int(_number(event.get('count'), 1))
        age = I._age(event.get('t'), now)
        right = (f'×{min(count, 999)} · ' if count > 1 else '') + age
        rw = min(inner * .33, pt.text_w(right, 10))
        _text(pt, PAD * 2 + 20, y + 19, identity, 11, width=max(1, inner - rw - 28), bold=True)
        _text(pt, width - PAD * 2 - rw, y + 19, right, 10, pt.p.muted, width=rw)
        _body_hit(hits, 'select', id, PAD, y, width - PAD * 2, 36, width, height, offset)
        _draw_paragraph(pt, summary, PAD * 2, y + 38, pt.p.text if event.get('status') == 'unread' or is_selected else pt.p.muted)
        detail_y = y + 38 + summary_h
        expand_h = summary_h + 6
        _body_hit(hits, 'expand', id, PAD, y + 36, width - PAD * 2, expand_h, width, height, offset)
        if body is not None:
            detail_y += 14
            _draw_paragraph(pt, body, PAD * 2, detail_y, pt.p.muted)
            detail_y += body_h + 2
        if reset is not None:
            _text(pt, PAD * 2, detail_y + 12, 'resets ' + V.fmt_span(reset - now), 10, pt.p.waiting, width=inner)
            detail_y += 24
        if is_open:
            button_y = y + card_h - 36
            bw = max(1, (inner - 7) / 2)
            for action, label, bx in (('jump', 'Jump ↵', PAD * 2), ('dismiss', 'Dismiss X', PAD * 2 + bw + 7)):
                pt.surface(bx, button_y, bw, 25, 9, .09 if action == 'jump' else .04, rim=.08)
                _text(pt, bx + 8, button_y + 12.5, label, 11, width=max(1, bw - 16), bold=action == 'jump')
                _body_hit(hits, action, id, bx, button_y, bw, 25, width, height, offset)
    pt.cr.restore()
    keys = [('Z', 'Z Undo')] if undo else []
    keys += [('D', 'D detail'), ('ENTER', '↵ jump'), ('X', 'X dismiss'), ('?', '?')]
    _footer(pt, hits, keys, width, height)
    surf.flush()
    return Rendered(surf, hits, content_height, selected_bounds)
