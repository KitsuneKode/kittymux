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
