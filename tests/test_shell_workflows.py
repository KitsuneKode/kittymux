#!/usr/bin/env python3
"""Shell/CLI regressions: private sockets, state and command mocks; no live kitty."""
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

MOCK = r'''#!/usr/bin/env python3
import json, os, pathlib, sys
root = pathlib.Path(os.environ['MOCK_ROOT'])
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
if name == 'kitty':
    with (root / 'calls').open('a') as f:
        f.write(json.dumps(args) + '\n')
    target = args[args.index('--to') + 1]
    states = json.loads((root / 'kitty.json').read_text())
    if target not in states:
        sys.exit('mock refuses non-private socket: ' + target)
    data = states[target]
    command = args[args.index('--to') + 2]
    if command == 'ls':
        print(json.dumps(data))
    elif command == 'launch':
        oid = int(os.environ.get('MOCK_LAUNCH_OS', '1'))
        ow = next(o for o in data if o['id'] == oid)
        var = args[args.index('--var') + 1] if '--var' in args else ''
        user_vars = dict([var.split('=', 1)]) if var else {}
        ow['tabs'].append({'id': 9, 'title': '!scratch', 'windows': [
            {'id': 99, 'user_vars': user_vars}]})
        (root / 'kitty.json').write_text(json.dumps(states))
        print(99)
    elif command == 'close-tab':
        tid = int(args[args.index('--match') + 1].split(':')[1])
        for ow in data:
            ow['tabs'] = [t for t in ow['tabs'] if t['id'] != tid]
        (root / 'kitty.json').write_text(json.dumps(states))
elif name == 'fzf':
    text = sys.stdin.read()
    with (root / 'fzf-input').open('a') as f:
        f.write(text)
    if '--print-query' in args:
        print('hello')
    elif os.environ.get('MOCK_FZF_CANCEL') != '1':
        print(text.splitlines()[0] if text.splitlines() else '')
elif name == 'fd':
    print((root / 'projects').read_text(), end='')
elif name == 'git':
    print({'alpha': '100', 'beta': '200', 'gamma': '300'}.get(pathlib.Path(args[1]).name, '0'))
elif name == 'hyprctl':
    print('[]')
'''


class ShellWorkflows(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='mux-shell-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(('KITTY', 'XDG_', 'MOCK_'))}
        bindir = self.root / 'bin'
        bindir.mkdir()
        for name in ('kitty', 'fzf', 'fd', 'git', 'hyprctl', 'notify-send'):
            script = bindir / name
            script.write_text(MOCK)
            script.chmod(0o755)
        self.env.update(PATH=str(bindir) + ':' + os.environ['PATH'],
                        HOME=str(self.root), SHELL='/bin/true',
                        KITTYMUX_STATE=str(self.root / 'state'),
                        XDG_RUNTIME_DIR=str(self.root), MOCK_ROOT=str(self.root))
        self.sockets = []
        self.targets = []
        for pid in (1001, 1002):
            path = self.root / f'mykitty-{pid}'
            sock = socket.socket(socket.AF_UNIX)
            sock.bind(str(path))
            self.sockets.append(sock)
            self.addCleanup(sock.close)
            self.targets.append('unix:' + str(path))
        self.env['KITTY_LISTEN_ON'] = self.targets[0]
        self.env['KITTYMUX_SOCKET_GLOB'] = str(self.root / 'mykitty-*')
        self.states = {s: self.window() for s in self.targets}
        self.save_states()

    @staticmethod
    def window(session='', active_session=None):
        w = {'id': 11, 'title': 'agent', 'cwd': '/project', 'session_name': session,
             'foreground_processes': [{'cmdline': ['claude']}], 'is_focused': False}
        tabs = [{'id': 7, 'title': 'regular', 'is_active': active_session is None, 'windows': [w]}]
        if active_session is not None:
            tabs.insert(0, {'id': 6, 'title': 'active', 'is_active': True,
                            'windows': [{'id': 10, 'session_name': active_session}]})
        return [{'id': 1, 'is_focused': True, 'tabs': tabs}]

    def save_states(self):
        (self.root / 'kitty.json').write_text(json.dumps(self.states))

    def run_shell(self, code, check=True):
        result = subprocess.run(['bash', '-c', code], cwd=ROOT, env=self.env,
                                text=True, capture_output=True, timeout=10)
        if check:
            self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def cli(self, name, *args, check=True):
        result = subprocess.run(['bash', str(ROOT / 'bin' / name), *args],
                                cwd=ROOT, env=self.env, text=True, capture_output=True, timeout=10)
        if check:
            self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def calls(self, command=None):
        path = self.root / 'calls'
        rows = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        return [r for r in rows if command is None or r[r.index('--to') + 2] == command]

    def test_regex_names(self):
        result = self.run_shell("source lib/mux.sh; regex_escape '-a.b+[x](y)'; regex_escape 'plain'")
        self.assertEqual(result.stdout.splitlines(), [r'\-a\.b\+\[x\]\(y\)', 'plain'])

    def test_no_trusted_socket_fails_closed(self):
        code = """source lib/socket.sh
mux_owned_socket() { return 1; }
mux_kitty_sockets() { :; }
unset KITTY_LISTEN_ON
s=$(mux_resolve_socket); rc=$?
printf '%s|%s' "$rc" "$s"
"""
        self.assertEqual(self.run_shell(code).stdout, '1|')

    def test_shared_caller_no_socket_does_not_call_kitty(self):
        result = self.run_shell("""source lib/mux.sh
KITTY_SOCKET=''
kitty_remote close-tab --match id:7
""", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_newtab_no_trusted_socket_never_calls_kitty(self):
        result = self.run_shell('''
source() {
    builtin source "$@"
    mux_owned_socket() { return 1; }
    mux_kitty_sockets() { :; }
}
unset KITTY_LISTEN_ON
source bin/mux-newtab.sh
''', check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_parent_wins_over_owned_stale_environment(self):
        result = self.run_shell("""source lib/socket.sh
python3 -c 'import socket,sys; s=socket.socket(socket.AF_UNIX); s.bind(sys.argv[1])' "$XDG_RUNTIME_DIR/mykitty-$PPID"
mux_resolve_socket
""")
        self.assertEqual(result.stdout, 'unix:' + str(self.root / f'mykitty-{os.getpid()}'))

    def test_explicit_target_and_fd(self):
        code = 'source lib/socket.sh; mux_resolve_socket "$KITTY_LISTEN_ON"; echo; KITTY_LISTEN_ON=fd:7 mux_resolve_socket'
        self.assertEqual(self.run_shell(code).stdout, self.targets[0] + '\nfd:7')
        result = self.run_shell('source lib/socket.sh; mux_resolve_socket unix:/nonexistent', check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '')

    def test_scratch_instances_with_same_ids_do_not_close_each_other(self):
        self.cli('mux-scratch.sh')
        self.env['KITTY_LISTEN_ON'] = self.targets[1]
        self.cli('mux-scratch.sh')
        self.assertEqual(self.calls('close-tab'), [])
        self.env['KITTY_LISTEN_ON'] = self.targets[0]
        self.cli('mux-scratch.sh')
        closed = self.calls('close-tab')
        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0][closed[0].index('--to') + 1], self.targets[0])

    def test_scratch_ignores_legacy_flag_for_regular_tab(self):
        runtime = self.root / 'kittymux'
        runtime.mkdir()
        (runtime / 'scratch-1').write_text('7\n')
        self.cli('mux-scratch.sh')
        self.assertEqual(self.calls('close-tab'), [])

    def test_scratch_stale_identity_and_os_ownership(self):
        self.cli('mux-scratch.sh')
        saved = json.loads((self.root / 'kitty.json').read_text())
        saved[self.targets[0]][0]['tabs'][-1]['title'] = 'regular'
        (self.root / 'kitty.json').write_text(json.dumps(saved))
        self.cli('mux-scratch.sh')
        self.assertEqual(self.calls('close-tab'), [])
        # Move the tracked scratch to another OS window: it is no longer ours to close.
        saved = json.loads((self.root / 'kitty.json').read_text())
        tab = saved[self.targets[0]][0]['tabs'].pop()
        saved[self.targets[0]].append({'id': 2, 'tabs': [tab]})
        (self.root / 'kitty.json').write_text(json.dumps(saved))
        self.cli('mux-scratch.sh')
        self.assertEqual(self.calls('close-tab'), [])

    def test_scratch_same_title_but_changed_launch_marker_is_not_closed(self):
        self.cli('mux-scratch.sh')
        saved = json.loads((self.root / 'kitty.json').read_text())
        saved[self.targets[0]][0]['tabs'][-1]['windows'][0]['user_vars']['kittymux_scratch'] = 'deadbeef'
        (self.root / 'kitty.json').write_text(json.dumps(saved))
        self.cli('mux-scratch.sh')
        self.assertEqual(self.calls('close-tab'), [])

    def test_scratch_no_trusted_socket_never_calls_kitty(self):
        # Wrap sourcing to keep all resolver trust checks private and negative.
        result = self.run_shell('''
source() {
    builtin source "$@"
    mux_owned_socket() { return 1; }
    mux_kitty_sockets() { :; }
}
unset KITTY_LISTEN_ON
source bin/mux-scratch.sh
''', check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('no trusted kitty socket', result.stderr)
        self.assertEqual(self.calls(), [])

    def test_scratch_unknown_trigger_aborts_without_launch(self):
        self.env['KITTY_WINDOW_ID'] = '404'
        result = self.cli('mux-scratch.sh', check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls('launch'), [])

    def test_shared_scratch_helper_uses_cli_namespace_and_validates(self):
        self.cli('mux-scratch.sh')
        result = self.run_shell('source lib/mux.sh; get_scratch_tab_id 1; scratch_win_id_for_os_window 1')
        self.assertEqual(result.stdout, '9\n99\n')
        self.env['KITTY_LISTEN_ON'] = self.targets[1]
        result = self.run_shell('source lib/mux.sh; get_scratch_tab_id 1', check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, '')

    def test_agent_picker_preserves_empty_and_named_sessions(self):
        for session, active in (('', None), ('named', None), ('parked', ''), ('', 'active')):
            with self.subTest(session=session, active=active):
                self.states = {self.targets[0]: self.window(session, active), self.targets[1]: []}
                self.save_states()
                (self.root / 'calls').unlink(missing_ok=True)
                self.cli('mux-agents.sh')
                focused = self.calls('focus-window')
                self.assertEqual(len(focused), 1)
                self.assertEqual(focused[0][focused[0].index('--to') + 1], self.targets[0])
                goto = [r for r in self.calls('action') if 'goto_session' in r]
                self.assertEqual([r[-1] for r in goto], [session] if session and active == '' else [])

    def test_agent_fields_cannot_break_tsv_rows(self):
        self.states[self.targets[1]] = []
        self.states[self.targets[0]][0]['tabs'][0]['windows'][0]['title'] = 'line\nwith\ttabs'
        self.save_states()
        rows = self.cli('mux-agents.sh', '--list').stdout.splitlines()
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(rows[0].split('\t')), 9)
        self.cli('mux-agents.sh')
        self.assertEqual(len(self.calls('focus-window')), 1)

    def test_attention_queue_preserves_socket_and_empty_sessions(self):
        self.states[self.targets[1]] = []
        self.save_states()
        state = self.root / 'state'
        state.mkdir()
        (state / 'panes-1001.json').write_text(json.dumps({'11': {'status': 'waiting', 'msg': 'permission required'}}))
        self.cli('mux-agents.sh', '--next-waiting')
        focused = self.calls('focus-window')
        self.assertEqual(len(focused), 1)
        self.assertEqual(focused[0][focused[0].index('--to') + 1], self.targets[0])
        self.assertEqual((state / 'next-waiting.last').read_text(), str(self.root / 'mykitty-1001') + ':11')
        self.cli('mux-agents.sh', '--next-waiting')  # wraparound path
        self.assertEqual(len(self.calls('focus-window')), 2)

    def test_attention_queue_does_not_skip_active_pane_in_an_inactive_tab(self):
        self.states = {self.targets[0]: self.window('', 'active'), self.targets[1]: []}
        agent_tab = self.states[self.targets[0]][0]['tabs'][1]
        agent_tab['windows'][0]['is_focused'] = True
        self.save_states()
        state = self.root / 'state'
        state.mkdir()
        (state / 'panes-1001.json').write_text(json.dumps({'11': {'status': 'waiting', 'msg': 'Approve?'}}))
        self.cli('mux-agents.sh', '--next-waiting')
        self.assertEqual(len(self.calls('focus-window')), 1)

    def test_send_contract_unchanged(self):
        self.states[self.targets[1]] = []
        self.save_states()
        rows = self.cli('mux-agents.sh', '--list').stdout.strip().split('\t')
        self.assertEqual(len(rows), 9)
        self.assertEqual(rows[4:6], ['', ''])
        self.cli('mux-send.sh')
        sent = self.calls('send-text')
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][sent[0].index('--to') + 1], self.targets[0])
        self.assertEqual(sent[0][-1], r'hello\r')

    def test_projects_sort_receives_stdin(self):
        projects = [str(self.root / n) for n in ('alpha', 'beta', 'gamma')]
        (self.root / 'projects').write_text('\n'.join(p + '/.git/' for p in projects) + '\n')
        sessions = self.root / 'state' / 'sessions'
        sessions.mkdir(parents=True)
        (sessions / '.history').write_text('alpha.kitty-session\n')
        self.env['MOCK_FZF_CANCEL'] = '1'
        self.cli('mux-projects.sh')
        self.assertEqual((self.root / 'fzf-input').read_text().splitlines(),
                         [projects[0], projects[2], projects[1]])


if __name__ == '__main__':
    unittest.main()
