"""Optional Kitty 0.50 pane dock. No-UI controller + event-driven strip UI."""
import os
import sys
import subprocess

from kittens.tui.handler import Handler, kitten_ui, result_handler
from kittens.tui.loop import Loop, MouseButton
from kittens.tui.operations import MouseTracking, set_cursor_position, styled
from kitty.key_encoding import EventType


def _paths():
    here = os.path.dirname(os.path.realpath(_paths.__code__.co_filename))
    for directory in (os.environ.get('KITTY_CONFIG_DIRECTORY', ''), here):
        if directory and directory not in sys.path:
            sys.path.insert(0, directory)
    return here


HERE = _paths()
import kittymux_panecontrols as controls  # noqa: E402


class Strip(Handler):
    mouse_tracking = MouseTracking.full

    def __init__(self, parent, socket):
        super().__init__()
        self.parent = parent
        self.socket = socket
        self.hits = []
        self.message = ''

    def initialize(self):
        self.draw_screen()

    def draw_screen(self):
        lines, self.hits = controls.strip(self.screen_size.cols)
        if self.message:
            lines[0] = self.message[:self.screen_size.cols]
        self.cmd.clear_screen()
        for y, line in enumerate(lines[:self.screen_size.rows]):
            self.write(set_cursor_position(0, y) + styled(line[:self.screen_size.cols], reverse=y > 0))
        self.flush()

    def on_resize(self, size):
        self.screen_size = size
        self.draw_screen()

    def act(self, action):
        # The controller passed this Kitty's own listener and immutable parent.
        # Native launch is not a kitten overlay: it does not supply a kitten RC FD.
        try:
            proc = subprocess.run(['kitten', '@', '--to', self.socket, 'kitten', '--match', f'id:{self.parent}',
                                   os.path.join(HERE, 'pane-controls-kit.py'), action, str(self.parent)],
                                  capture_output=True, text=True, timeout=4)
        except (OSError, subprocess.TimeoutExpired):
            self.message = 'Action unavailable; retry from the pane'
            self.draw_screen()
            return
        self.message = (proc.stdout.strip() if proc.returncode == 0 else 'Action failed; use CLI for details')
        if action != 'hide':
            self.draw_screen()

    def on_click(self, event):
        if event.buttons != MouseButton.LEFT:
            return
        for action, x, y, width in self.hits:
            if event.cell_y == y and x <= event.cell_x < x + width:
                self.act(action)
                return

    def on_mouse_move(self, event):
        for action, x, y, width in self.hits:
            if event.cell_y == y and x <= event.cell_x < x + width:
                self.message = controls.LABELS[controls.ACTIONS.index(action)]
                self.draw_screen()
                return

    def on_key_event(self, event, in_bracketed_paste=False):
        if event.type == EventType.RELEASE:
            return
        key = (event.key or '').upper()
        keys = {'R': 'split-right', 'D': 'split-down', 'Z': 'zoom', 'T': 'move-to-tab', 'X': 'close',
                'MINUS': 'hide', 'Q': 'hide', 'ESCAPE': 'hide'}
        if key in keys:
            self.act(keys[key])


@kitten_ui()
def main(args):
    if len(args) != 4 or args[1] != '--ui':
        return ''
    parent, socket = args[2:]
    if parent.isdecimal() and int(parent) > 0 and socket.startswith('unix:'):
        Loop().loop(Strip(int(parent), socket))
    return ''


@result_handler(no_ui=True)
def handle_result(args, answer, target_window_id, boss):
    from kitty.constants import kitty_exe, version
    try:
        # Require both the RC matched window and immutable explicit parent.
        if len(args) != 3 or not args[2].isdecimal() or int(args[2]) != target_window_id:
            raise ValueError('explicit parent does not match the target pane')
        return controls.operate(boss, target_window_id, args[1], version,
                                os.path.join(HERE, 'pane-controls-kit.py'), kitty_exe())
    except (ValueError, OSError) as error:
        # A string beginning ERROR is decoded by the CLI as a refused action.
        return 'ERROR: ' + str(error)
