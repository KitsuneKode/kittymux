"""Optional Kitty 0.50 pane dock. No-UI controller + themed event-driven strip UI."""
import os
import sys
import subprocess

from kittens.tui.handler import Handler, kitten_ui, result_handler
from kittens.tui.loop import Loop, MouseButton
from kittens.tui.operations import MouseTracking, set_cursor_position, styled
from kitty.fast_data_types import Color
from kitty.key_encoding import EventType


def _paths():
    here = os.path.dirname(os.path.realpath(_paths.__code__.co_filename))
    for directory in (os.environ.get('KITTY_CONFIG_DIRECTORY', ''), here):
        if directory and directory not in sys.path:
            sys.path.insert(0, directory)
    return here


HERE = _paths()
import kittymux_panecontrols as controls  # noqa: E402
import kittymux_theme as theme  # noqa: E402


def _color(rgb: int) -> Color:
    return Color((rgb >> 16) & 0xFF, (rgb >> 8) & 0xFF, rgb & 0xFF)


class Strip(Handler):
    mouse_tracking = MouseTracking.full

    def __init__(self, parent, socket):
        super().__init__()
        self.parent = parent
        self.socket = socket
        self.hits = []
        self.hovered = None
        self.message = ''
        self.is_error = False
        self.palette = theme.from_colors({})

    def initialize(self):
        self.palette = theme.palette_from_kitty(self.socket)
        self.draw_screen()

    def draw_screen(self):
        rows, self.hits = controls.styled_strip(
            self.screen_size.cols,
            self.palette,
            hovered=self.hovered,
            message=self.message,
            is_error=self.is_error,
        )
        self.cmd.clear_screen()
        for y, segs in enumerate(rows[:self.screen_size.rows]):
            out = set_cursor_position(0, y)
            rem = self.screen_size.cols
            for seg in segs:
                if rem <= 0:
                    break
                chunk = seg.text[:rem]
                rem -= len(chunk)
                out += styled(chunk, fg=_color(seg.fg), bg=_color(seg.bg), bold=seg.bold)
            self.write(out)
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
            self.is_error = True
            self.draw_screen()
            return
        reply = proc.stdout.strip()
        refused = reply.startswith('ERROR:')
        self.is_error = proc.returncode != 0 or refused
        self.message = (reply if proc.returncode == 0 else 'Action failed; use CLI for details')
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
        hit = None
        for action, x, y, width in self.hits:
            if event.cell_y == y and x <= event.cell_x < x + width:
                hit = action
                break
        if hit != self.hovered:
            self.hovered = hit
            if hit is not None:
                self.message = ''
                self.is_error = False
            self.draw_screen()

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
