"""Read rice's existing T3 usage cache; no token, RPC, fetch, or second collector.

Only presentation fields cross the boundary. The cache lives beside the supplied
kittymux state directory, so private rigs cannot accidentally read the real one.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import time

import kittymux_meters as M
import kittymux_place

MAX_AGE = 7 * 86400
MAX_BYTES = 512 * 1024


def clean(value, limit=80):
    return kittymux_place.clean(str(value or ''))[:limit]


def adapt(document, *, now=None):
    now = time.time() if now is None else now
    if not isinstance(document, dict) or not isinstance(document.get('providers'), list):
        return None
    cached = M.num(document.get('cachedAt'))
    if cached is None or cached <= 0 or now - cached / 1000 > MAX_AGE or cached / 1000 - now > 300:
        return None
    providers = []
    for raw in document['providers'][:32]:
        if not isinstance(raw, dict):
            continue
        name = clean(raw.get('driver'), 40)
        if not re.fullmatch(r'[a-z][a-z0-9_-]{0,39}', name):
            continue
        accounts, rows, samples = [], [], []
        raw_accounts = raw.get('accounts')
        for i, account in enumerate(raw_accounts[:16] if isinstance(raw_accounts, list) else []):
            if not isinstance(account, dict):
                continue
            label = clean(account.get('name')) or f'Account {i + 1}'
            sample = M.num(account.get('checkedAt'))
            windows = account.get('windows')
            account_rows = []
            for window in windows[:32] if isinstance(windows, list) else []:
                if not isinstance(window, dict):
                    continue
                window_label = clean(window.get('label') or window.get('kind') or 'Quota', 40)
                used, reset, duration = (M.num(window.get(k)) for k in ('used', 'resetsAt', 'durationMins'))
                row = {'label': window_label}
                if reset and reset / 1000 <= now:
                    row['text'] = 'reset passed · awaiting a new sample'
                elif used is None:
                    row['text'] = 'quota unknown'
                else:
                    row['pct'] = max(0.0, min(100.0, used))
                    if reset and reset > 0:
                        row['rem_s'] = max(0, reset / 1000 - now)
                    if duration and duration > 0:
                        row['window_s'] = duration * 60
                account_rows.append(row)
                rows.append(dict(row, label=f'{label} · {window_label}'))
            if account_rows:
                accounts.append({'label': label, 'rows': account_rows, 'plan': clean(account.get('plan'), 40)})
                if sample and sample > 0 and sample / 1000 <= now + 300:
                    samples.append(sample / 1000)
        if accounts:
            providers.append({'name': name, 'rows': rows, 'accounts': accounts,
                              'sample_ts': min(samples) if len(samples) == len(accounts) else None,
                              'sample_age_unknown': len(samples) != len(accounts),
                              'note': 'T3 Code cache shared by rice · ' + clean(raw.get('label') or name)})
    return {'ts': cached / 1000, 'source': 't3-cached', 'providers': providers} if providers else None


def shared(state_dir, local, *, now=None):
    """Prefer a recent shared cache, retaining local providers absent from it."""
    try:
        with (Path(state_dir).parent / 'rice' / 'usage-t3.json').open('rb') as stream:
            data = stream.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            return local
        result = adapt(json.loads(data), now=now)
        if result:
            names = {p['name'] for p in result['providers']}
            existing = local.get('providers') if isinstance(local, dict) else None
            result['providers'] += [p for p in existing[:32] if isinstance(p, dict) and p.get('name') not in names] if isinstance(existing, list) else []
            return result
    except (OSError, ValueError, TypeError):
        pass
    return local
