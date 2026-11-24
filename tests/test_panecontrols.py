"""Pane controls bind an explicit parent in one running kitty, never the focus."""
import importlib.machinery
import importlib.util
from pathlib import Path
import sys
import os
import shutil
import subprocess
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'python'))
import kittymux_panecontrols as P


class ControlsTests(unittest.TestCase):
    def parent(self):
        tab = SimpleNamespace(id=2, list_groups=lambda: [{'id': 7, 'windows': [7]}],
                              current_layout=SimpleNamespace(name='splits', layout_state=lambda: {}))
        group = SimpleNamespace(dock=None, docks=[])
        tab.windows = SimpleNamespace(group_for_window=lambda w: group)
        return SimpleNamespace(id=7, os_window_id=4, user_vars={}, tabref=lambda: tab)

    def boss(self):
        parent = self.parent()
        return SimpleNamespace(window_id_map={7: parent}, active_window=SimpleNamespace(id=99),
                               call_remote_control=Mock(return_value='8'), run_kitten_with_metadata=Mock(), _move_window_to=Mock())

    def test_running_version_gate_fails_closed_before_mutation(self):
        for version in [(0, 49, 2), (), '0.50.0', None]:
            boss = self.boss()
            with self.assertRaisesRegex(ValueError, 'running Kitty 0.50'):
                P.operate(boss, 7, 'show', version, '/synthetic/pane-controls-kit.py', 'kitty')
            boss.call_remote_control.assert_not_called()
        self.assertTrue(P.supported((0, 50, 0)))
        self.assertTrue(P.supported((1, 0, 0)))

    def test_missing_or_invalid_parent_never_falls_back_to_focus(self):
        for wid in (0, -1, True, '7', 99):
            with self.assertRaisesRegex(ValueError, 'parent'):
                P.operate(self.boss(), wid, 'close', (0, 50, 0), '/synthetic/pane-controls-kit.py', 'kitty')

    def test_show_pins_native_dock_and_source_without_taking_focus(self):
        boss = self.boss()
        P.operate(boss, 7, 'show', (0, 50, 0), '/synthetic/pane-controls-kit.py', 'kitty')
        parent, cmd = boss.call_remote_control.call_args.args
        self.assertEqual(parent.id, 7)
        for arg in ('--type=window-dock', '--dock-edge=top', '--dock-skip-focus', '--keep-focus',
                    '--next-to=id:7', '--source-window=id:7', '--match=window_id:7'):
            self.assertIn(arg, cmd)

    def test_failed_remote_launch_is_reported_instead_of_claiming_shown(self):
        boss = self.boss()
        boss.call_remote_control.return_value = '0'
        with self.assertRaisesRegex(ValueError, 'did not create'):
            P.operate(boss, 7, 'show', (0, 50, 0), '/synthetic/pane-controls-kit.py', 'kitty')

    def test_show_is_idempotent_hide_closes_only_owned_dock(self):
        boss = self.boss()
        parent = boss.window_id_map[7]
        owned = SimpleNamespace(id=8, user_vars={P.MARK: '7'})
        unrelated = SimpleNamespace(id=9, user_vars={P.MARK: '7'})
        group = parent.tabref().windows.group_for_window(parent)
        group.docks.append(SimpleNamespace(windows=[owned]))
        boss.window_id_map.update({8: owned, 9: unrelated})
        P.operate(boss, 7, 'show', (0, 50, 0), '/synthetic/pane-controls-kit.py', 'kitty')
        boss.call_remote_control.assert_not_called()
        P.operate(boss, 7, 'hide', (0, 50, 0), '/synthetic/pane-controls-kit.py', 'kitty')
        self.assertEqual(boss.call_remote_control.call_args.args[1], ('close-window', '--match=id:8'))

    def test_actions_target_parent_after_focus_changes(self):
        for action in ('split-right', 'split-down', 'move-to-tab', 'zoom'):
            boss = self.boss()
            P.operate(boss, 7, action, (0, 50, 0), '/synthetic/pane-controls-kit.py', 'kitty')
            for call in boss.call_remote_control.call_args_list:
                parent, cmd = call.args
                self.assertEqual(parent.id, 7)
                self.assertTrue('--match=id:7' in cmd or '--match=window_id:7' in cmd)
                self.assertNotIn('id:99', cmd)

    def test_close_uses_existing_guard_on_explicit_parent(self):
        boss = self.boss()
        P.operate(boss, 7, 'close', (0, 50, 0), '/synthetic/pane-controls-kit.py', 'kitty')
        boss.call_remote_control.assert_not_called()
        call = boss.run_kitten_with_metadata.call_args
        self.assertEqual(call.args[0], '/synthetic/close-kit.py')
        self.assertEqual(call.kwargs['window'].id, 7)
        self.assertEqual(call.kwargs['args'], ('window', 'pane-controls close'))

    def test_move_to_tab_stays_in_original_os_window_after_focus_moves(self):
        boss = self.boss()
        parent = boss.window_id_map[7]
        parent.os_window_id = 4
        boss._move_window_to = Mock()
        P.operate(boss, 7, 'move-to-tab', (0, 50, 0), '/synthetic/pane-controls-kit.py', 'kitty')
        boss._move_window_to.assert_called_once_with(window=parent, target_tab_id='new', target_os_window_id=4)

    def test_zoom_restores_both_two_pane_split_orientations(self):
        for horizontal in (True, False):
            boss = self.boss()
            tab = boss.window_id_map[7].tabref()
            tab.current_layout.layout_state = lambda: {'pairs': {'one': 7, 'two': 8, 'horizontal': horizontal},
                'maximized': [{'window_id': 7, 'is_horizontal': horizontal}]}
            P.operate(boss, 7, 'zoom', (0, 50, 0), '/synthetic/pane-controls-kit.py', 'kitty')
            actions = [c.args[1] for c in boss.call_remote_control.call_args_list if c.args[1][0] == 'action']
            self.assertEqual(actions, [('action', '--match=id:7', 'layout_action', 'maximize', 'horizontal' if horizontal else 'vertical')])

    def test_narrow_layout_keeps_every_action_reachable(self):
        for width in (1, 8, 18, 26, 80):
            lines, hits = P.strip(width)
            self.assertEqual({h[0] for h in hits}, set(P.ACTIONS))
            self.assertTrue(all(len(line) <= max(8, width) for line in lines))

    def test_narrow_strip_uses_whole_short_labels(self):
        lines, _ = P.strip(26)
        self.assertIn('◫ Right', lines[1])
        self.assertIn('⬓ Down', lines[1])
        self.assertIn('↗ Tab', lines[2])
        self.assertNotIn('--help', lines[0])

    def test_styled_strip_uses_theme_surfaces_and_distinct_hover(self):
        import kittymux_theme as T
        for colors in (
            {'background': 0x1a1b26, 'foreground': 0xc0caf5, 'color9': 0xf7768e, 'color10': 0x9ece6a, 'color12': 0x7aa2f7},
            {'background': 0xf6f8fc, 'foreground': 0x0f172a, 'color9': 0xc11f49, 'color10': 0x2f7d32, 'color12': 0x253d63},
        ):
            pal = T.from_colors(colors)
            for width in (8, 18, 26, 60):
                rows, hits = P.styled_strip(width, pal, hovered='zoom')
                self.assertEqual(len(rows), 3)
                self.assertEqual({h[0] for h in hits}, set(P.ACTIONS))
                for row in rows:
                    self.assertEqual(sum(len(seg.text) for seg in row), max(8, width))
                row1_bgs = {seg.bg for seg in rows[1]}
                self.assertIn(pal.card, row1_bgs)
                self.assertIn(pal.card_hi, row1_bgs)
                self.assertIn(pal.bar, row1_bgs)
            rows_close, _ = P.styled_strip(40, pal, hovered='close')
            self.assertIn('Close pane', ''.join(s.text for s in rows_close[0]))


class CLITests(unittest.TestCase):
    def test_own_listener_wins_even_without_window_id(self):
        with patch.dict('os.environ', {'KITTY_LISTEN_ON': 'unix:/own', 'KITTYMUX_TARGET': 'unix:/other'}, clear=True), \
             patch.object(self.cli, '_own_kitty_socket', return_value='unix:/own'), \
             patch.object(self.cli, '_owned_socket', return_value=True), \
             patch.object(self.cli, '_run', return_value=(0, 'shown')) as run:
            self.assertEqual(self.cli.pane_controls_cmd(['show', '--window', '7']), 0)
        self.assertIn('unix:/own', run.call_args.args[0])

    def test_valid_arguments_without_a_socket_use_standard_execution_failure(self):
        with patch.dict('os.environ', {'KITTY_WINDOW_ID': '7'}, clear=True), \
             patch.object(self.cli, '_own_kitty_socket', return_value=None), \
             patch.object(self.cli, '_no_socket', return_value=1) as error:
            self.assertEqual(self.cli.pane_controls_cmd(['show']), 1)
            error.assert_called_once_with('pane-controls')

    def test_window_option_uses_shared_missing_value_error(self):
        with self.assertRaisesRegex(self.cli.kittymux_cliargs.UsageError, '--window needs a value'):
            self.cli.pane_controls_cmd(['show', '--window'])

    @unittest.skipUnless(shutil.which('kitty'), 'Kitty interpreter missing')
    def test_dock_ui_initializes_with_a_unix_listener_without_an_inherited_fd(self):
        code = "import runpy; m=runpy.run_path(" + repr(str(ROOT / 'python/pane-controls-kit.py')) + "); m['main'].initialize()"
        env = dict(os.environ, KITTY_LISTEN_ON='unix:/synthetic/owned-socket')
        run = subprocess.run(['kitty', '+runpy', code], env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(run.returncode, 0, run.stderr)

    @classmethod
    def setUpClass(cls):
        loader = importlib.machinery.SourceFileLoader('panecontrols_cli_test', str(ROOT / 'bin/kittymux'))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        cls.cli = importlib.util.module_from_spec(spec)
        loader.exec_module(cls.cli)

    def test_inside_kitty_uses_own_socket_over_target_override(self):
        with patch.dict('os.environ', {'KITTY_WINDOW_ID': '7', 'KITTYMUX_TARGET': 'unix:/other'}, clear=True), \
             patch.object(self.cli, '_own_kitty_socket', return_value='unix:/own'), \
             patch.object(self.cli, '_run', return_value=(0, 'shown')) as run:
            self.assertEqual(self.cli.pane_controls_cmd([]), 0)
        self.assertIn('unix:/own', run.call_args.args[0])
        self.assertIn('id:7', run.call_args.args[0])

    def test_outside_requires_explicit_owned_socket_and_parent(self):
        with patch.dict('os.environ', {}, clear=True), patch.object(self.cli, '_run') as run:
            self.assertEqual(self.cli.pane_controls_cmd([]), 2)
            run.assert_not_called()
        with patch.dict('os.environ', {'KITTYMUX_TARGET': 'unix:/synthetic', 'KITTY_WINDOW_ID': ''}, clear=True), \
             patch.object(self.cli, '_own_kitty_socket', return_value=None), \
             patch.object(self.cli, '_owned_socket', return_value=True), \
             patch.object(self.cli, '_run', return_value=(0, 'shown')) as run:
            self.assertEqual(self.cli.pane_controls_cmd(['show', '--window', '7']), 0)
            self.assertIn('unix:/synthetic', run.call_args.args[0])

    def test_invalid_parent_refused_before_remote_command(self):
        with patch.dict('os.environ', {'KITTY_WINDOW_ID': '7'}, clear=True), patch.object(self.cli, '_run') as run:
            self.assertEqual(self.cli.pane_controls_cmd(['show', '--window', '-1']), 2)
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
