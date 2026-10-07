"""Validated contexts and argv orchestration for the shell key-binding entry points."""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import stat
import tempfile
import time
from kittymux_files import positive_id


@dataclass(frozen=True)
class Context:
    os_id: int
    tab_id: int
    window_id: int
    host: dict
    tab: dict
    window: dict


def contexts(data):
    if not isinstance(data, list):
        raise ValueError('invalid kitty snapshot')
    out = []
    for host in data[:128]:
        if not isinstance(host, dict) or not positive_id(host.get('id')) or not isinstance(host.get('tabs'), list):
            raise ValueError('invalid OS window')
        for tab in host['tabs'][:4096]:
            if not isinstance(tab, dict) or not positive_id(tab.get('id')) or not isinstance(tab.get('windows'), list):
                raise ValueError('invalid tab')
            for window in tab['windows'][:4096]:
                if not isinstance(window, dict) or not positive_id(window.get('id')):
                    raise ValueError('invalid pane')
                out.append(Context(host['id'], tab['id'], window['id'], host, tab, window))
    return out


def context(data, source=''):
    all_contexts = contexts(data)
    if source:
        if not str(source).isdecimal() or int(source) <= 0:
            raise ValueError('invalid source pane')
        found = next((c for c in all_contexts if c.window_id == int(source)), None)
    else:
        found = next((c for c in all_contexts if c.host.get('is_focused') and c.tab.get('is_active') and c.window.get('is_focused')), None)
        found = found or next((c for c in all_contexts if c.host.get('is_focused') and c.tab.get('is_active')), None)
    if not found:
        raise ValueError('cannot identify source pane')
    return found


def cycle(names, current, direction):
    if not names:
        raise ValueError('no live sessions')
    if current not in names:
        return names[0]
    return names[(names.index(current) + (-1 if direction == 'prev' else 1)) % len(names)]


def active_context(target):
    tab = next((t for t in target.host['tabs'] if t.get('is_active')), target.tab)
    if not tab['windows']:
        raise ValueError('active tab is closing; retry after it settles')
    window = next((w for w in tab['windows'] if w.get('is_active') or w.get('is_focused')), tab['windows'][0])
    return tab, window


def scratch_record(tab):
    if not isinstance(tab, dict) or tab.get('title') != '!scratch' or not positive_id(tab.get('id')):
        return None
    for window in tab.get('windows', []):
        variables = window.get('user_vars')
        token = variables.get('kittymux_scratch') if isinstance(variables, dict) else None
        if positive_id(window.get('id')) and isinstance(token, str) and re.fullmatch('[0-9a-f]{32}', token):
            return f"{tab['id']}\t{window['id']}\t{token}"
    return None


def runtime_dir(state_dir):
    base = os.environ.get('XDG_RUNTIME_DIR', '')
    if base and os.path.isdir(base) and os.stat(base).st_uid == os.getuid():
        path = Path(base, 'kittymux')
    else:
        path = Path(state_dir, 'run')
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink() or path.stat().st_uid != os.getuid():
        raise ValueError('untrusted runtime directory')
    path.chmod(0o700)
    return path


def scratch_path(sock, os_id, state_dir):
    path = sock.removeprefix('unix:')
    info = os.stat(path)
    if not sock.startswith('unix:') or not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid() or not positive_id(os_id):
        raise ValueError('untrusted scratch owner')
    key = hashlib.sha256(f'{path}:{info.st_dev}:{info.st_ino}'.encode()).hexdigest()
    return runtime_dir(state_dir) / f'scratch-{key}-{os_id}'


def read_record(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as f:
            info = os.fstat(f.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
                return None
            raw = f.read(1025)
        return raw.decode('ascii').strip() if len(raw) <= 1024 else None
    except (OSError, UnicodeError):
        return None


def run(argv, sock, call, snapshot, state_dir):
    """call takes RC argv, returns (status, text); all paths remain argv elements."""
    if not argv:
        return 2
    op, args = argv[0], argv[1:]
    def rc(*parts):
        return call(['kitty', '@', '--to', sock, *parts], 8)
    def ls(*parts):
        status, raw = rc('ls', *parts)
        if status or len(raw.encode()) > 8 * 1024 * 1024:
            raise ValueError('kitty snapshot unavailable')
        data = json.loads(raw)
        contexts(data)
        return data
    source = os.environ.get('KITTY_WINDOW_ID', '')
    # Remote control supplies the calling overlay identity to kitty itself.
    c = context(snapshot, source)
    if source:
        status, raw = rc('ls', '--match', 'state:overlay_parent')
        parents = [] if status else json.loads(raw) if len(raw.encode()) <= 8 * 1024 * 1024 else []
        parent = next((p for p in contexts(parents) if p.os_id == c.os_id and p.tab_id == c.tab_id and p.window_id != c.window_id), None)
        c = parent or c
    if op == 'nav':
        action = args[0] if args else 'next'
        if len(args) > 1 or (action not in ('prev', 'next') and (not action.isdecimal() or int(action) < 1)):
            return 2
        name = c.window.get('session_name', '')
        tabs = [t for t in c.host['tabs'] if name and any(w.get('session_name') == name for w in t['windows'])]
        if not tabs:
            action = 'previous_tab' if action == 'prev' else 'next_tab' if action == 'next' else f'goto_tab {int(action)}'
            return rc('action', '--match', f'id:{c.window_id}', action)[0]
        ids = [t['id'] for t in tabs]
        if action.isdecimal():
            if int(action) > len(ids):
                return 1
            target = ids[int(action)-1]
        else:
            target = cycle(ids, c.tab_id, action)
        return rc('focus-tab', '--match', f'id:{target}')[0]
    if op == 'newtab':
        if any(a not in ('--home', '--next') for a in args):
            return 2
        cwd = os.path.expanduser('~') if '--home' in args else 'current'
        scratch = next((t for t in c.host['tabs'] if scratch_record(t)), None)
        location, target = ('after', c.tab_id) if '--next' in args and c.tab is not scratch else ('before', scratch['id']) if scratch else ('last', c.tab_id)
        return rc('launch', '--type=tab', '--match', f'id:{target}', '--source-window', f'id:{c.window_id}', '--cwd', cwd, '--location', location)[0]
    if op == 'scratch':
        cwd, command = os.path.expanduser('~'), []
        while args:
            part, args = args[0], args[1:]
            if part == '--cwd':
                if not args: return 2
                cwd, args = args[0], args[1:]
            elif part == '--':
                command = args; break
            else:
                command.append(part)
        path = scratch_path(sock, c.os_id, state_dir)
        record = read_record(path)
        old = next((t for t in c.host['tabs'] if record and scratch_record(t) == record), None)
        if path.is_symlink():
            raise ValueError('untrusted scratch record')
        # Create first, so invocation from the old scratch has a live source.
        token = secrets.token_hex(16)
        launch = ['launch', '--type=tab', '--match', f'window_id:{c.window_id}', '--tab-title', '!scratch', '--var', 'kittymux_scratch='+token, '--cwd', cwd, '--location', 'last']
        if command: launch += ['--', *command]
        status, raw = rc(*launch)
        if status: return status
        if not raw.strip().isdecimal(): raise ValueError('invalid launched pane')
        created = next((x for x in contexts(ls()) if x.window_id == int(raw.strip()) and x.os_id == c.os_id), None)
        if not created or scratch_record(created.tab) != f'{created.tab_id}\t{created.window_id}\t{token}':
            raise ValueError('scratch launch identity unavailable')
        fd, tmp = tempfile.mkstemp(prefix='.scratch-', dir=path.parent)
        try:
            with os.fdopen(fd, 'w') as f: f.write(scratch_record(created.tab)+'\n')
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp): os.unlink(tmp)
        if old:
            # Refresh before the destructive operation; never trust an old snapshot.
            fresh = next((t for h in ls() if h['id'] == c.os_id for t in h['tabs'] if scratch_record(t) == record), None)
            if fresh: return rc('close-tab', '--match', f"id:{fresh['id']}")[0]
        return 0
    if op == 'find-session' and len(args) == 1:
        data = ls('--match-tab', 'session:^'+re.escape(args[0])+'$')
        host = next((h for h in data if h['tabs']), None)
        if not host: return 1
        print(host['id']); return 0
    if op == 'save-session' and len(args) == 2:
        wid, path = args
        target = context(snapshot, wid)
        active_tab, active_window = active_context(target)
        name = active_window.get('session_name', '')
        selected = [w for t in target.host['tabs'] for w in t['windows'] if w.get('session_name', '') == name]
        selected_ids = {w['id'] for w in selected}
        selected_tabs = [t for t in target.host['tabs'] if any(w['id'] in selected_ids for w in t['windows'])]
        focus = next((i for i, t in enumerate(selected_tabs) if t['id'] == active_tab['id']), 0)
        match = ' or '.join('id:' + str(w['id']) for w in selected)
        if not match:
            return 1
        final = Path(path)
        if final.is_symlink():
            raise ValueError('untrusted session destination')
        final.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        # Native save is async. A private pending directory keeps the last good
        # file available until capture and its single-OS focus correction succeed.
        with tempfile.TemporaryDirectory(prefix='.pending-native-', dir=final.parent) as pending:
            capture = Path(pending, 'capture.kitty-session')
            action = shlex.join(['--save-only', '--use-foreground-process', '--match='+match, str(capture)])
            status, _ = rc('action', '--match', f'id:{target.window_id}', 'save_as_session', action)
            if status:
                return status
            deadline = time.monotonic() + 6
            while not capture.is_file() and time.monotonic() < deadline:
                time.sleep(.05)
            with capture.open('rb') as f:
                raw = f.read(8 * 1024 * 1024 + 1)
            if len(raw) > 8 * 1024 * 1024:
                raise ValueError('session capture too large')
            lines = raw.decode('utf-8').splitlines()
            # Kitty indexes focus against all original tabs, even when filtered.
            # This helper captures one OS window, so normalize its first prefix.
            seen_tab = False
            normalized = []
            for line in lines:
                if not seen_tab and line.strip() == 'new_os_window':
                    continue
                if line.startswith('new_tab'):
                    seen_tab = True
                normalized.append(f'focus_tab {focus}' if line.startswith('focus_tab ') else line)
            fd, tmp = tempfile.mkstemp(prefix='.session-', dir=final.parent)
            try:
                with os.fdopen(fd, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(normalized)+'\n')
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, final)
            finally:
                if os.path.exists(tmp): os.unlink(tmp)
        return 0
    if op in ('session-names', 'session-current', 'session-active', 'session-cycle', 'session-last') and args:
        target = context(snapshot, args[0])
        history_path = Path(state_dir, 'sessions', f'.live-history-{target.os_id}')
        try:
            with history_path.open() as f: history = f.read(65536).splitlines()[:50]
        except OSError: history = []
        files = sorted((f for f in Path(state_dir, 'sessions').glob('*') if f.is_file() and f.suffix in ('.kitty-session', '.kitty_session', '.session')), key=lambda f:f.stat().st_mtime, reverse=True)
        live = {str(w.get('session_name')) for t in target.host['tabs'] for w in t['windows'] if w.get('session_name')}
        ordered = list(dict.fromkeys(n for n in history+[f.stem for f in files] if n in live))
        active_tab, active_window = active_context(target)
        active = active_window.get('session_name', '')
        active = active if active in ordered else ''
        if op == 'session-names': print('\n'.join(ordered)) if ordered else None
        elif op == 'session-active': print(active) if active else None
        elif op == 'session-current': print(active or (ordered[0] if ordered else ''))
        elif op == 'session-last':
            previous = next((n for n in history if n in ordered and n != active), '')
            print(previous) if previous else None
        elif op == 'session-cycle':
            if len(args) != 2 or args[1] not in ('prev', 'next'): return 2
            print(cycle(ordered, active, args[1]))
        return 0
    return 2
