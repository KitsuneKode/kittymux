import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
import kittymux_workflows as W

class WorkflowTests(unittest.TestCase):
    def snapshot(self):
        return [{'id':1,'is_focused':False,'tabs':[{'id':2,'is_active':True,'title':'work','windows':[{'id':3,'is_focused':True,'session_name':'calm-otter'}]}]}, {'id':4,'is_focused':True,'tabs':[{'id':5,'is_active':True,'title':'other','windows':[{'id':6,'is_focused':True}]}]}]
    def test_source_window_outranks_focus_and_unknown_never_targets_other_window(self):
        self.assertEqual(W.context(self.snapshot(), '3').os_id, 1)
        with self.assertRaises(ValueError): W.context(self.snapshot(), '999')
        self.assertEqual(W.context(self.snapshot(), '').os_id, 4)
    def test_invalid_ids_and_malformed_roots_rejected(self):
        for data in ({}, [{'id':True,'tabs':[]}], [{'id':1,'tabs':'bad'}]):
            with self.assertRaises(ValueError): W.context(data, '')
    def test_cycle_and_scratch_identity(self):
        self.assertEqual(W.cycle(['a','b','c'], 'a', 'prev'), 'c')
        self.assertEqual(W.cycle(['a','b'], 'unknown', 'next'), 'a')
        tab={'id':2,'title':'!scratch','windows':[{'id':3,'user_vars':{'kittymux_scratch':'a'*32}}]}
        self.assertEqual(W.scratch_record(tab), '2\t3\t'+'a'*32)
        tab['title']='unrelated';self.assertIsNone(W.scratch_record(tab))

class LastTests(unittest.TestCase):
    """alt+0 jumps to the last real tab, ctrl+alt+0 to the last pane."""

    def world(self, scratch=True, session='calm-otter'):
        def tab(i, wins, title='t', extra=None):
            ws = [{'id': w, 'is_focused': w == wins[0], 'session_name': session, **(extra or {})} for w in wins]
            return {'id': i, 'is_active': i == 10, 'title': title, 'windows': ws}
        tabs = [tab(10, [101, 102, 103]), tab(11, [111]), tab(12, [121])]
        if scratch:
            tabs.append(tab(13, [131], '!scratch', {'user_vars': {'kittymux_scratch': 'a' * 32}}))
        return [{'id': 1, 'is_focused': True, 'tabs': tabs}]

    def run_op(self, args, data, env_id='101'):
        import tempfile
        from unittest import mock
        calls = []
        def rc(argv, timeout):
            calls.append(argv)
            return 0, '[]'
        with tempfile.TemporaryDirectory() as d, mock.patch.dict('os.environ', {'KITTY_WINDOW_ID': env_id}):
            status = W.run(args, 'unix:/private', rc, data, d)
        return status, [c for c in calls if c[4:5] != ['ls']]

    def test_nav_last_skips_the_scratch_tab_and_stays_in_the_session(self):
        status, calls = self.run_op(['nav', 'last'], self.world())
        self.assertEqual(status, 0)
        self.assertEqual(calls, [['kitty', '@', '--to', 'unix:/private', 'focus-tab', '--match', 'id:12']])

    def test_nav_last_with_only_the_scratch_tab_goes_there_and_without_a_session_uses_every_tab(self):
        data = self.world(scratch=True)
        data[0]['tabs'] = [t for t in data[0]['tabs'] if t['id'] == 13]
        status, calls = self.run_op(['nav', 'last'], data, '131')
        self.assertEqual(calls[-1][-1], 'id:13')
        bare = self.world(session='')
        for t in bare[0]['tabs']:
            for w in t['windows']:
                w.pop('session_name', None)
        status, calls = self.run_op(['nav', 'last'], bare)
        self.assertEqual(calls[-1][-2:], ['--match', 'id:12'])

    def test_pane_last_focuses_the_highest_numbered_pane_of_this_tab_only(self):
        status, calls = self.run_op(['pane', 'last'], self.world())
        self.assertEqual(status, 0)
        self.assertEqual(calls, [['kitty', '@', '--to', 'unix:/private', 'focus-window', '--match', 'id:103']])
        status, calls = self.run_op(['pane', 'last'], self.world(), '111')
        self.assertEqual(calls[-1][-1], 'id:111')                      # a one-pane tab: itself

    def test_bad_arguments_change_nothing(self):
        for args in (['pane'], ['pane', 'first'], ['pane', 'last', 'x'], ['nav', 'last', 'x'], ['nav', '0'], ['nav', '-1']):
            status, calls = self.run_op(args, self.world())
            self.assertEqual((status, calls), (2, []), args)

class WorkflowArgvTests(unittest.TestCase):
    def test_empty_active_tab_during_close_fails_before_any_remote_action(self):
        import tempfile
        from unittest import mock
        data = WorkflowTests().snapshot()
        data[0]['tabs'][0]['is_active'] = False
        data[0]['tabs'].append({'id': 7, 'is_active': True, 'windows': []})
        def rc(argv, timeout):
            raise AssertionError('no remote action during an incomplete snapshot')
        with tempfile.TemporaryDirectory() as d, mock.patch.dict('os.environ', {'KITTY_WINDOW_ID': ''}):
            for args in (['save-session', '3', str(Path(d, 'calm.kitty-session'))], ['session-current', '3']):
                with self.subTest(args=args), self.assertRaises(ValueError):
                    W.run(args, 'unix:/private', rc, data, d)

    def test_save_path_and_match_keep_exact_argv_and_source_owner(self):
        import shlex, tempfile
        from unittest import mock
        data=WorkflowTests().snapshot();calls=[]
        def rc(argv, timeout):
            calls.append(argv)
            if 'save_as_session' in argv:
                Path(shlex.split(argv[-1])[-1]).write_text('new_tab calm\nlaunch sh\nfocus_tab 0\n')
                return 0,''
            return 1,''
        with tempfile.TemporaryDirectory() as d, mock.patch.dict('os.environ',{'KITTY_WINDOW_ID':'3'}):
            path=Path(d,"synthetic 'quote\nname.kitty-session")
            self.assertEqual(W.run(['save-session','3',str(path)],'unix:/private',rc,data,d),0)
            self.assertIn('launch sh',path.read_text())
            args=shlex.split(calls[-1][-1])
            self.assertEqual(Path(args[-1]).parent.parent,path.parent)
            self.assertIn('--match=id:3',args)
            self.assertNotIn('id:6',calls[-1][-1])

    def test_named_save_excludes_parked_sessions_in_the_same_os_window(self):
        import json, tempfile
        from unittest import mock
        data=WorkflowTests().snapshot()
        data[0]['tabs'].insert(0,{'id':7,'is_active':False,'windows':[{'id':8,'session_name':'parked-bird'}]})
        calls=[]
        def rc(argv, timeout):
            calls.append(argv)
            if 'save_as_session' in argv:
                import shlex
                Path(shlex.split(argv[-1])[-1]).write_text('new_os_window\nnew_tab calm\nlaunch sh\nfocus_tab 1\n')
            return 0,json.dumps([])
        with tempfile.TemporaryDirectory() as d, mock.patch.dict('os.environ',{'KITTY_WINDOW_ID':'3'}):
            path=Path(d,'calm-otter.kitty-session')
            self.assertEqual(W.run(['save-session','3',str(path)],'unix:/private',rc,data,d),0)
            text=path.read_text()
            self.assertFalse(text.startswith('new_os_window'))
            self.assertIn('focus_tab 0',text)
            self.assertNotIn('id:8',calls[-1][-1])

    def test_unknown_explicit_socket_cannot_fall_back(self):
        import kittymux_sockets as S
        self.assertIsNone(S.target(lambda:'unix:/valid',[],lambda p:False,{'KITTYMUX_TARGET':'unix:/invalid'}))

class SocketHandleTests(unittest.TestCase):
    def test_native_inherited_socket_handle_is_preserved_but_closed_fd_rejected(self):
        import socket
        import kittymux_sockets as S
        first, second = socket.socketpair()
        with first as endpoint, second:
            # Own fd is a real socket, unlike an arbitrary environment string.
            handle='fd:'+str(endpoint.fileno())
            self.assertEqual(S.target(lambda:None,[],lambda p:False,{'KITTYMUX_TARGET':handle}),handle)
        self.assertIsNone(S.target(lambda:'unix:/other',[],lambda p:True,{'KITTYMUX_TARGET':handle}))
