# Conventions and hard-won mechanics

How kitty behaves underneath us (reload, redraw cost, clicks, the divider, hit-testing, kittens) and the rules that follow. Read it before touching the tab bar, bar sizing, the layout engine, a kitten or anything that runs on a timer.

Part of the agent guide: start at [AGENTS.md](../../AGENTS.md) (the rules and the "read before you change" table); this page is the reference for one area.

- Runtime state under `$KITTYMUX_STATE` else `$XDG_STATE_HOME/kittymux`;
  panes/usage caches are per-kitty-PID (`panes-<pid>.json`).
- Python files run under kitty's bundled interpreter — `kitty.*` and
  `kittens.*` are importable there, not under system python.
- `# key — description` comments in the conf feed `bin/mux-keys.py` (the
  `ctrl+alt+/` overlay). Keep the comment format so docs never drift.
- Ownership: kitty owns tabs/panes/sessions; the WM owns OS-window borders
  and global chords — check `hyprctl binds` before taking a `ctrl+alt+` key.
- **kitty caches watcher modules per path for the life of the process** — `on_load` and `pane-state.py` run once.
  Anything that must pick up an upgrade on `load_config` lives in a `kittymux_*.py` helper: `tab_bar.py` (re-run on every config reload) refreshes EVERY kittymux module the process has imported, dependencies first (`kittymux_reload.reload_all` — a hand-kept list
  missed the helpers imported lazily on first use, so a day-old inbox/sockets module served a new scanner), then restarts what runs on timers: `kittymux_scan.restart()`, `kittymux_barsize.install()`.
- Long-lived state (timer ids etc.) lives in `sys.modules["_kittymux_scan_rt"]`, never in plain module
  globals — a reload re-executes the file and would forget a live timer (→ stacked timers = leak).
- **A look is verified by looking.** Before and after a visual change render the bar with `tests/shot_bar.sh` (and the panel with `tests/shot_panel.sh`, narrow too: a 26-column panel found three layout bugs unit tests missed) (dark AND light, the 30-column bar and the narrowest one) and read the PNG — unit tests did not catch a hue
  palette of four near-identical greens that sat next to the "done" colour. A tint stays quieter than the state colours; the name is the one bright thing on a row.
- **Redraw = three calls**: `tm.update_tab_bar_data()`, `tm.mark_tab_bar_dirty()`, then `mark_os_window_dirty(id)` +
  `wakeup_main_loop()`. The first two only update cells; without the last two kitty does not render until the
  cursor blinks (a 10 fps spinner ran at ~1 fps on an idle window). Use `kittymux_scan.refresh_bar`.
- `sys.path`: a module's OWN directory must win over the config dir (insert config first, own last),
  or tests/rigs silently import the installed copy instead of the code under test.
- `kittymux_barsize` keeps its drag/button state in `sys.modules["_kittymux_barsize_rt"]`: changing the width makes kitty
  re-run `tab_bar.py` (→ reloads helper modules) in the middle of a drag, and module globals would be wiped (the first
  motion applied a width, the second found no drag). Same rule as the scanner.
- Redraw cost: kitty redraws the whole vertical bar tab by tab (~10×/s while an agent works). Shared lookups (palette, merged pane state, verdict roll-ups, keyboard mode, usage alert, native-edge check)
  are memoised PER PASS (`tab_bar._per_pass`, reset when tab 1 is drawn): 6.0 → 2.1 ms with 23 tabs. Don't add per-tab `os.stat`/file reads/subprocesses to the draw path; add a `@_per_pass` helper. The spinner
  ticks unfocused OS windows at half rate. `_flush` does not even serialise verdicts on a tick where no verdict changed.
- Tab clicks (kitty 0.49.2 `TabManager.handle_tab_bar_mouse`): a left PRESS only arms a drag; the tab is activated on the left RELEASE and only if `MouseEvents.is_click` holds — press+release within
  `click_interval`, **< 5 px apart**, same tab — while a drag needs `drag_threshold` (we set 14 so a wobbly click is not a drag). Movement of 5–14 px was therefore neither: the click silently did nothing
  (real mice/touchpads wobble this much, more on a scaled display; scripted clicks never do). `kittymux_barsize._tap_before/_tap_after` record the press and, when kitty did not act, activate the tab under a rule
  that matches the drag threshold (≤ max(5, drag_threshold) px, ≤ 1.5 s, same tab, no drag started). A middle-click on a tab running an agent is swallowed (kitty closes tabs on middle-click, and only asks if
  `confirm_os_window_close` says so). Smoke tests MUST click with wobble (`tests/smoke_click.sh`): a perfect click hides this whole class of bug.
- Bar drag-resize (`kittymux_barsize`): per mouse event `apply_width(final=False)` re-lays-out the bar and ONLY the visible tab; the release (or the watchdog /
  an error, via `_end_capture(finalize=True)`) applies `final=True` once for every tab. Events inside the pacing window are NOT dropped: `next_apply` arms one
  trailing timer that applies the pointer's latest width (the old code left the bar stuck until release after a fast burst). Why not relayout every tab per event:
  kitty itself retains ~100 objects (~14 MB per 1000) per option-change+relayout of 23 tabs (measured identical in a vanilla kitty), so touching one tab is 28× less.
  The pointer over the tab bar is ALWAYS a hand: kitty picks it in C for the whole bar rect, sends our code no hover and ignores OSC 22 there — a resize cursor over the bar
  edge is not possible (only real window dividers and the docked panel get one).
- Native divider (kitty ≥ 0.49.2, `kittymux_barsize._install_native_edge`): we wrap `kitty.borders.set_borders_rects` to add (a) two coloured `Border` rects — colour `(rgb << 8) | BorderColor.window_bg`, exact
  pixels, drawn by kitty's GPU border renderer in the pane padding next to the bar — and (b) one invisible hit rect (`border_type` < 0 = left edge, > 0 = right) over them. kitty hit-tests it IN C
  (`mouse_region`): hover → native `sb_h_double_arrow`, press → `Boss.drag_resize_start` (we answer for our rect), then `drag_resize_update/_end` until release, cursor restored by C. C only runs
  border hit-tests when the tab has 2+ visible windows, and the cursor over the tab bar rect is ALWAYS a hand (`in_tab_bar` → `POINTER_POINTER`) and the bar gets no motion events ("expensive and useless"
  in `handle_tab_bar_mouse`). So: split tabs get the arrow, single-pane tabs the bar-side grab zone. Wrappers must delegate to module-level functions by name (a reload re-executes this module in place);
  they never raise; the hook costs ~35 µs per border refresh and retains nothing. `L.edge_geometry` is the pure geometry; `tests/smoke_native.sh` reads the real X cursor and pixels.
- The divider (cell fallback: padding < 10 px, or a kitty we have not verified) is two hairlines in the bar's last two columns (`tab_bar.SEP_COLS`, `SEP_EIGHTS`); content stays left of them. The resize hit area is `kittymux_layout.in_grab_zone`: centred on
  the seam between them (`DIVIDER_CELLS`), ±`GRAB_CELLS` — exactly those two columns — so it never steals a click meant for a tab; the collapse button stops where it starts.
  Right-edge bars still draw the divider on the screen-side (outer) edge: a known limitation, not mirrored yet.
- The header row's `«`/`»` is a button: `kittymux_barsize._handle` consumes its press+release and toggles
  full ↔ rail via a saved layout + `load_config_file`. Build the toggled layout from the LIVE bar when nothing was saved.
- kitty caps every vertical tab's HEIGHT at `tab_title_max_lines` (kittymux.conf sets 4): a tab that draws more rows spills into
  the spacer row (no gap, no hairline, wrong extent). The first tab's header (2 rows) + title + subtitle must fit in the cap —
  `kittymux_layout.header_rows` degrades to a 1-row header when the cap is 3.
- kitty ≥ 0.49.2 reorders dragged tabs by INSERTION (`TabBar.tab_insertion_target_at`, drop marker, `TabBeingDropped(tab_id, tab_ids)`);
  our 0.49.1 drag patches check `kittymux_barsize.native_insert_drag()` and stand down (only `_drop_spans` is nudged so the first tab's
  header does not count). Never touch `TabBeingDropped` without checking its fields.
- Tab drag-and-drop (0.49.1): kitty's first `on_tab_drop_move` of a drag has x=y=0 and seeds the dragged tab at the END (it jumped to the
  top of a vertical bar); `kittymux_barsize.make_on_tab_drop_move` seeds the real order, and `make_tab_id_at` applies
  `kittymux_layout.drag_target` (a tab counts only past its midpoint) so unequal tab heights cannot cascade swaps.
- Vertical-bar hit testing: kitty's tab extents skip the spacer line between tabs; `kittymux_barsize` wraps
  `TabBar.tab_id_at` (`kittymux_layout.snap_tab_id`) so drag-sorting and clicks on the gap resolve to the nearer tab.
- Python kittens are `exec`'d, not imported — no `__file__`, use
  `KITTY_CONFIG_DIRECTORY`; `styled()` wants `Color` objects, not ints/strings.
