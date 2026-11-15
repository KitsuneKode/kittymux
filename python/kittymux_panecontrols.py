"""Explicit-parent pane actions; no focus guessing, polling or persistent state.

Native docks are created in Kitty's own event loop so concurrent `show` requests
cannot make duplicate strips. Imports here also work in plain Python tests.
"""
from pathlib import Path
import os

import kittymux_zoom

MARK = 'kittymux_pane_controls'
ACTIONS = ('split-right', 'split-down', 'zoom', 'move-to-tab', 'close', 'hide')
LABELS = ('R Split right', 'D Split down', 'Z Zoom', 'T Move to tab', 'X Close', '- Hide')


def supported(version) -> bool:
    return (isinstance(version, (tuple, list)) and len(version) >= 3
            and all(type(x) is int for x in version[:3]) and tuple(version[:3]) >= (0, 50, 0))


def strip(width: int):
    """Three rows, with all six pointer targets even in an eight-column pane.

    Labels shorten with the viewport; the CLI lists the full names and provides
    the keyboard equivalent because a skip-focus dock never intercepts typing.
    """
    width = max(8, width)
    cell = max(2, (width - 2) // 3)
    lines = ['Pane controls - kittymux pane-controls --help'[:width]]
    hits = []
    for row in range(2):
        pieces = []
        for col in range(3):
            index = row * 3 + col
            label = LABELS[index]
            if len(label) > cell:
                label = ('R Right', 'D Down', 'Z Zoom', 'T Tab', 'X Close', '- Hide')[index]
            text = label[:cell].ljust(cell)
            pieces.append(text)
            hits.append((ACTIONS[index], col * (cell + 1), row + 1, cell))
        lines.append(' '.join(pieces))
    return lines, hits


def _parent(boss, parent_id):
    if type(parent_id) is not int or parent_id <= 0:
        raise ValueError('invalid parent pane ID')
    parent = boss.window_id_map.get(parent_id)
    if parent is None or parent.tabref() is None:
        raise ValueError('parent pane no longer exists; no action taken')
    tab = parent.tabref()
    group = tab.windows.group_for_window(parent)
    if group is None or group.dock is not None:
        raise ValueError('parent must be a normal pane, not a dock')
    return parent, tab, group


def operate(boss, parent_id, action, version, kit_path, kitty_exe):
    """Run inside the target Kitty. Every action is pinned to parent_id.

    The running process's version, not the executable on disk, is authoritative.
    Only native dock children with our marker can be hidden. Close of the parent
    always enters the existing guard; its confirmation policy stays authoritative.
    """
    if not supported(version):
        raise ValueError('pane controls require running Kitty 0.50 or newer; no action taken')
    parent, tab, group = _parent(boss, parent_id)
    if action not in (*ACTIONS, 'show', 'toggle'):
        raise ValueError('unknown pane control action')
    match = f'--match=id:{parent_id}'
    def rc(*cmd):
        result = boss.call_remote_control(parent, tuple(cmd))
        if cmd[0] == 'launch' and (result is None or str(result) == '0'):
            raise ValueError('Kitty did not create the requested pane')
        return result

    owned = [w for dock in group.docks for w in dock.windows
             if w.user_vars.get(MARK) == str(parent_id)]
    if action in ('show', 'hide', 'toggle'):
        if action == 'hide' or (action == 'toggle' and owned):
            for dock in owned:
                rc('close-window', f'--match=id:{dock.id}')
            return 'hidden'
        if owned:
            return 'shown'
        rc('launch', f'--match=window_id:{parent_id}', f'--source-window=id:{parent_id}',
           f'--next-to=id:{parent_id}', '--type=window-dock', '--dock-edge=top', '--dock-size=3',
           '--dock-skip-focus', '--keep-focus', '--spacing=padding=0', '--spacing=margin=0',
           f'--var={MARK}={parent_id}', '--title=kittymux-pane-controls',
           kitty_exe, '+runpy', 'from kittens.runner import main; main()',
           os.environ.get('KITTY_CONFIG_DIRECTORY', str(Path(kit_path).parent)), kit_path, '--ui', str(parent_id),
           getattr(boss, 'listening_on', ''))
        return 'shown'
    if action == 'close':
        boss.run_kitten_with_metadata(str(Path(kit_path).with_name('close-kit.py')),
                                      args=('window', 'pane-controls close'), window=parent)
        return 'close requested - repeat to confirm a busy agent'
    if action in ('split-right', 'split-down'):
        rc('launch', f'--match=window_id:{parent_id}', f'--source-window=id:{parent_id}',
           f'--next-to=id:{parent_id}', '--location=' + ('vsplit' if action == 'split-right' else 'hsplit'),
           '--cwd=current', '--keep-focus')
    elif action == 'move-to-tab':
        rc('detach-window', match, '--target-tab=new')
    elif action == 'zoom':
        state = {'groups': tab.list_groups(), 'layout_state': tab.current_layout.layout_state()}
        steps = kittymux_zoom.zoom_actions(tab.current_layout.name, kittymux_zoom.maximized_axes(state, parent_id))
        if steps:
            # layout_action operates on the tab's active group even when matched.
            # This deliberate user action selects its original parent first.
            rc('focus-window', match)
            for step in steps:
                rc('action', match, *step)
    return action
