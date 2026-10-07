"""Generated, allowlisted support facts. Never archive runtime files or raw doctor text."""
import io
import json
import os
import platform
import re
import tarfile
import tempfile
import time
from pathlib import Path
from kittymux_files import read_json
STATES = ('limited', 'waiting', 'working', 'done', 'idle')

def summary(state_dir, version, kitty_version, features, env=None):
    env = os.environ if env is None else env
    system = platform.system()
    system = system if system in ('Linux', 'Darwin', 'Windows', 'FreeBSD') else 'Other'
    kv = re.search('\\b(\\d{1,3}\\.\\d{1,3}\\.\\d{1,3})\\b', str(kitty_version)[:4096])
    counts = {s: 0 for s in STATES}
    instances = panes = 0
    try:
        paths = sorted(Path(state_dir).glob('scan-*.json'))[:128]
    except OSError:
        paths = []
    for path in paths:
        if not re.fullmatch('scan-\\d+\\.json', path.name):
            continue
        scan = read_json(path, {}, limit=512 * 1024)
        instances += 1
        for wid, record in list(scan.items())[:4096]:
            if not str(wid).isdigit() or not isinstance(record, dict):
                continue
            panes += 1
            state = record.get('state')
            if isinstance(state, str) and state in counts:
                counts[state] += 1
    allowed = ('folder', 'hue', 'collide', 'panetitle', 'sheet', 'hover')
    return {'schema': 1, 'kittymux': version, 'kitty': kv.group(1) if kv else 'unavailable', 'platform': system, 'display': 'wayland' if env.get('WAYLAND_DISPLAY') else 'x11' if env.get('DISPLAY') else 'none', 'features': {k: bool(features.get(k, False)) for k in allowed}, 'published_state': {'instances': instances, 'panes': panes, 'states': counts}}

def bundle(directory, facts):
    directory = Path(directory).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    data = json.dumps(facts, sort_keys=True, indent=2).encode()
    if len(data) > 64 * 1024:
        raise ValueError('diagnostics exceeded the safe size limit')
    manifest = b'kittymux generated diagnostics (schema 1)\nIncluded: diagnostics.json (allowlisted versions, platform, boolean features, counts)\nExcluded: config, environment, raw doctor output, paths, sockets, titles, commands,\nagent/session identities, journals, logs, inbox bodies and screen text.\nNo runtime file is archived. This bundle is created locally; nothing is uploaded.\n'
    fd, path = tempfile.mkstemp(prefix=time.strftime('kittymux-doctor-%Y%m%d-%H%M%S-'), suffix='.tar.gz', dir=directory)
    try:
        with os.fdopen(fd, 'wb') as f, tarfile.open(fileobj=f, mode='w:gz') as archive:
            for name, raw in (('MANIFEST.txt', manifest), ('diagnostics.json', data)):
                info = tarfile.TarInfo(name)
                info.size = len(raw)
                info.mode = 0o600
                info.mtime = 0
                archive.addfile(info, io.BytesIO(raw))
    except Exception:
        os.unlink(path)
        raise
    return path
