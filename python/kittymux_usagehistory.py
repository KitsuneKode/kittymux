"""Bounded numeric quota samples. No titles, accounts, commands or provider bodies."""
import fcntl
import json
import math
import os
import tempfile
import time
from kittymux_files import read_json
PROVIDERS = frozenset(('codex', 'claude', 'cursor', 'devin'))

def record(state_dir, providers, now=None):
    now = time.time() if now is None else now
    if not math.isfinite(now):
        return
    os.makedirs(state_dir, mode=0o700, exist_ok=True)
    lock = os.open(os.path.join(state_dir, 'usage-trends.lock'), os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = os.path.join(state_dir, 'agent-usage-trends.json')
        data = read_json(path, {'version': 1, 'samples': []}, limit=256 * 1024)
        prior = data.get('samples', []) if isinstance(data.get('samples'), list) else []
        samples = []
        for s in prior[-2048:]:
            if not isinstance(s, dict) or not isinstance(s.get('provider'), str) or s['provider'] not in PROVIDERS:
                continue
            row, at, pct = (s.get('row'), s.get('at'), s.get('pct'))
            if not isinstance(row, int) or isinstance(row, bool) or (not 0 <= row < 16):
                continue
            if not all((isinstance(v, (int, float)) and (not isinstance(v, bool)) and math.isfinite(v) for v in (at, pct))):
                continue
            if not now - 48 * 3600 <= at <= now or not 0 <= pct <= 100:
                continue
            samples.append({'provider': s['provider'], 'row': row, 'at': at, 'pct': pct})
        for p in providers[:16]:
            if not isinstance(p, dict) or not isinstance(p.get('name'), str) or p['name'] not in PROVIDERS:
                continue
            for i, r in enumerate(p.get('rows', [])[:16] if isinstance(p.get('rows'), list) else []):
                if not isinstance(r, dict) or r.get('clock'):
                    continue
                v = r.get('pct')
                if not isinstance(v, (int, float)) or isinstance(v, bool) or (not math.isfinite(v)):
                    continue
                stamp = r.get('_live_ts') if r.get('_live') else now
                if not isinstance(stamp, (int, float)) or isinstance(stamp, bool) or not math.isfinite(stamp) or not now - 48 * 3600 <= stamp <= now:
                    continue
                observed = int(stamp // 3600) * 3600
                samples = [s for s in samples if (s.get('provider'), s.get('row'), s.get('at')) != (p['name'], i, observed)]
                samples.append({'provider': p['name'], 'row': i, 'at': observed, 'pct': min(100, max(0, v))})
        fd, tmp = tempfile.mkstemp(prefix='.usage-trends-', dir=state_dir)
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump({'version': 1, 'samples': samples[-2048:]}, f)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    finally:
        os.close(lock)
