import os
import sys
import types
import unittest
from unittest import mock
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
import kittymux_scan as S

class QuitCaptureTests(unittest.TestCase):
    def test_registration_replaces_only_our_callback(self):
        other = lambda *a: None
        watches = types.SimpleNamespace(on_quit=[other])
        module = types.ModuleType('kitty.window')
        module.global_watchers = lambda: watches
        with mock.patch.dict(sys.modules, {'kitty.window': module}):
            S._install_quit_capture(); S._install_quit_capture()
        self.assertEqual(watches.on_quit, [other, S._quit_capture])
    def test_cancel_and_disabled_never_serialize(self):
        boss = mock.Mock()
        with mock.patch.object(S, '_autosave_enabled', return_value=True):
            S._quit_capture(boss, None, {'confirmed': False})
        with mock.patch.object(S, '_autosave_enabled', return_value=False):
            S._quit_capture(boss, None, {'confirmed': True})
        boss.serialize_state_as_session.assert_not_called()
    def test_native_capture_restores_vars_and_hands_off_anonymous_fd(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            window = types.SimpleNamespace(user_vars={'kittymux_sid': 'stale', 'kept': 'value'}, child=types.SimpleNamespace(foreground_processes=[]))
            def serialize(**kw):
                self.assertNotIn('kittymux_sid', window.user_vars)
                self.assertTrue(kw['ser_opts'].use_foreground_process)
                yield 'new_tab saved'
                yield 'launch sh'
            boss = types.SimpleNamespace(all_windows=[window], serialize_state_as_session=serialize)
            session = types.ModuleType('kitty.session')
            session.default_save_as_session_opts = lambda: types.SimpleNamespace()
            resume = types.SimpleNamespace(identify=lambda *a: None)
            def launch(argv, **kw):
                self.assertEqual(os.read(kw['pass_fds'][0], 4096), b'new_tab saved\nlaunch sh\n')
                self.assertIn('finalize', argv)
            with mock.patch.dict(sys.modules, {'kitty.session': session}), mock.patch.object(S, 'state_dir', return_value=d), mock.patch.object(S, '_autosave_enabled', return_value=True), mock.patch.object(S, '_journal_mod', return_value=(None, resume)), mock.patch.object(S, '_journal_agents', return_value={}), mock.patch.object(S.subprocess, 'Popen', side_effect=launch), mock.patch.object(S, '_record'), mock.patch.dict(vars(S._RT), {'exit_captured': False}), mock.patch.dict(os.environ, {'KITTYMUX_PANEL': '0'}):
                S._quit_capture(boss, window, {'confirmed': True})
                self.assertTrue(S._RT.exit_captured)
            self.assertEqual(window.user_vars, {'kittymux_sid': 'stale', 'kept': 'value'})

    def test_failed_capture_keeps_original_vars_and_does_not_mark_success(self):
        window = types.SimpleNamespace(user_vars={'kittymux_sid': 'stale'}, child=types.SimpleNamespace(foreground_processes=[]))
        boss = types.SimpleNamespace(all_windows=[window], serialize_state_as_session=mock.Mock(side_effect=RuntimeError('synthetic')))
        session = types.ModuleType('kitty.session')
        session.default_save_as_session_opts = lambda: types.SimpleNamespace()
        resume = types.SimpleNamespace(identify=lambda *a: None)
        with mock.patch.dict(sys.modules, {'kitty.session': session}), mock.patch.object(S, '_autosave_enabled', return_value=True), mock.patch.object(S, '_journal_mod', return_value=(None, resume)), mock.patch.object(S, '_journal_agents', return_value={}), mock.patch.object(S, '_record') as record, mock.patch.object(S, '_debug'), mock.patch.dict(vars(S._RT), {'exit_captured': False}), mock.patch.dict(os.environ, {'KITTYMUX_PANEL': '0'}):
            S._quit_capture(boss, window, {'confirmed': True})
            self.assertFalse(S._RT.exit_captured)
            self.assertEqual(record.call_args.kwargs['outcome'], 'exit capture failed')
        self.assertEqual(window.user_vars, {'kittymux_sid': 'stale'})
