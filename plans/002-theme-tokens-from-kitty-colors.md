# Plan 002: Derive all UI colours from the live kitty theme via a shared token module

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 8681a7d..HEAD -- python/ install.sh README.md AGENTS.md`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED (visual change to the always-visible tab bar; pure-logic parts are unit-tested)
- **Depends on**: plans/001-fix-agent-icon-color-and-cwd-heredoc.md
- **Category**: dx / bug (design system)
- **Planned at**: commit `8681a7d`, 2026-09-29

## Why this matters

`python/tab_bar.py` and `python/sidebar-kit.py` hardcode the Catppuccin Mocha
palette (`0x1e1e2e`, `0xcba6f7`, …). The user's terminal theme is gruvbox
(`background #272727`) and is switched dynamically by their HyDE setup, so the
tab bar renders as a navy/purple slab that clashes with the terminal. The same
agent glyph/brand tables are copy-pasted in `tab_bar.py` and `sidebar-kit.py` and
already disagree (aider is `✎` in one, `📝` in the other). This plan introduces
one pure-Python **token module** that derives every UI colour from kitty's
*current* colours (so it follows theme changes), one shared **agent table**, and
switches both consumers to them. It changes colours only — layout redesign is
plan 003.

## Current state

- `python/tab_bar.py` — custom tab bar; hardcoded palette at the top:

```python
# Catppuccin Mocha
_BG          = as_rgb(0x1e1e2e)  # base
_SESSION_FG  = as_rgb(0x89b4fa)  # blue
_ACTIVE_FG   = as_rgb(0xcba6f7)  # mauve
_INACTIVE_FG = as_rgb(0x6c7086)
_ACTIVITY_FG = as_rgb(0xa6e3a1)  # unread output
_WAITING_FG  = as_rgb(0xb4befe)  # agent idle, needs input
_SEP_FG      = as_rgb(0x313244)
_BRACKET_FG  = as_rgb(0x45475a)
_CWD_FG      = as_rgb(0x9399b2)
_BRANCH_FG   = as_rgb(0xa6e3a1)
...
_AGENT_GLYPHS = {"claude": "", "codex": "", "cursor-agent": "", ...,
                 "aider": "✎", "crush": "♥", "grok": "✗"}
_AGENT_BRANDS = {"claude": 0xd97757, "codex": 0x10a37f, ...}
_ALERT_FG = as_rgb(0xf38ba8)
```

- `python/sidebar-kit.py` — `kitten` overlay run in a *separate process*
  (`kitten_ui(allow_remote_control=True)`); duplicated tables `_GLYPHS`, `_BRANDS`
  (`Color` objects via `_C(rgb)`), and palette `_MAUVE _TEXT _DIM _FAINT _ROW_BG
  _EDGE _SKY _INDIGO _EMERALD`. It reads env `KITTY_CONFIG_DIRECTORY`.
- Kitty facts (verified against `/usr/lib/kitty/kitty/tab_bar.py`, kitty 0.49.1):
  - `draw_tab(draw_data: DrawData, screen, tab: TabBarData, ...)`. `DrawData` has
    `Color` fields `active_fg, active_bg, inactive_fg, inactive_bg, default_bg`;
    `default_bg` = `tab_bar_background or background`. `int(color)` gives `0xRRGGBB`.
  - `screen.cursor.fg/bg` need *tagged* ints: `as_rgb(x) == (x << 8) | 2`.
  - Custom `tab_bar.py` is loaded with `runpy.run_path(<config_dir>/tab_bar.py)`, so
    `__file__` is defined there (it is a symlink to this repo's file; use
    `os.path.realpath`). `get_options()` (from `kitty.fast_data_types`) returns the
    live options object (has `.background`, `.foreground`, …).
  - Kittens run in a separate process and are `exec`'d — **no `__file__`**. Get colours
    via remote control: `main.remote_control(["get-colors", "--configured"],
    capture_output=True, text=True)` prints lines like `background #272727`,
    `color12 #83a597` (kitty.conf syntax).
- `install.sh` symlinks only `tab_bar.py` into `~/.config/kitty` (lines ~54–62).
- Conventions (from `AGENTS.md`): Python kittens must import `kitty.*` only inside
  kitty's interpreter; keep `# key — description` comment format in `.tpl`
  untouched; README's key table must stay in sync with the `.tpl` (not affected).

### Token design (implement exactly)

Pure functions over plain `0xRRGGBB` ints — **no `kitty` imports** so they are
unit-testable under system `python3`:

- `blend(fg: int, bg: int, w: float) -> int` — per-channel `round(fg*w + bg*(1-w))`.
- `luminance(c)`, `contrast(a, b)` — WCAG relative luminance / ratio.
- `ensure_contrast(fg, bg, minimum=3.0)` — blend `fg` toward white/black (whichever
  the theme leans away from) in 5% steps until `contrast >= minimum`; return fg.
- `dim(c, f=0.55)` — scale channels (used for inactive agent brand marks).
- `Palette` (frozen dataclass of ints): `bg, fg, text, muted, faint, surface,
  surface_hi, accent, working, waiting, done, alert, info`.
- `from_colors(c: dict[str, int]) -> Palette` where `c` is a mapping with keys
  `background`, `foreground`, optional `active_border_color`, and `color1..color15`:
  - `bg = c["background"]`, `fg = c["foreground"]`, `text = fg`
  - `muted = blend(fg, bg, 0.62)`, `faint = blend(fg, bg, 0.40)`
  - `surface = blend(fg, bg, 0.07)`, `surface_hi = blend(fg, bg, 0.13)`
  - `accent`: env `KITTYMUX_ACCENT` (`#rrggbb`) if set, else `active_border_color`,
    else `color12`
  - status colours use the *bright* ANSI slots and pass through
    `ensure_contrast(..., bg, 3.0)`: `working = color14` (cyan), `waiting = color11`
    (yellow — "needs you"), `done = color10` (green), `alert = color9` (red),
    `info = color12` (blue)
  - missing keys fall back to `fg`/`muted` — never raise.
- `parse_kitty_colors(text: str) -> dict[str, int]` — parse `get-colors` output
  (`name #rrggbb` per line; ignore `none` and malformed lines).

Agent table (`python/kittymux_agents.py`, also pure): `AGENTS: dict[str, Agent]`
with `Agent(glyph: str, brand: int)` using the *current* values from `tab_bar.py`
(`_AGENT_GLYPHS`/`_AGENT_BRANDS`); for the three fallback glyphs use the tab-bar
versions (`aider ✎`, `crush ♥`, `grok ✗`) — the sidebar's emoji variants are
dropped. Provide `agent_in(cmdline_args: Iterable[str]) -> str | None` returning
the first arg whose basename (lowercased) is in `AGENTS`.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Unit tests | `python3 -m unittest discover -s tests -v` | all pass |
| Syntax | `python3 -m py_compile python/*.py` | exit 0 |
| Shell syntax | `bash -n install.sh` | exit 0 |
| Shellcheck | `shellcheck -S warning install.sh` | no *new* warnings vs. `git stash`-baseline (existing: SC2034 kitty_minor, SC2174) |
| Scratch kitty | see Step 6 | renders |

## Suggested executor toolkit

- Read `/usr/lib/kitty/kitty/tab_bar.py` (lines 47–110) for `TabBarData`/`DrawData`/`as_rgb`.
- Docs: https://sw.kovidgoyal.net/kitty/kittens/custom/ (kitten remote control),
  https://sw.kovidgoyal.net/kitty/remote-control/ (`get-colors`).

## Scope

**In scope**:
- `python/kittymux_theme.py` (create), `python/kittymux_agents.py` (create)
- `tests/test_theme.py` (create), `tests/test_agents.py` (create)
- `python/tab_bar.py`, `python/sidebar-kit.py`
- `install.sh` (symlink the two new modules), `AGENTS.md` (Layout list), `README.md` (Layout tree)

**Out of scope**:
- Any layout/geometry change to `tab_bar.py`/`sidebar-kit.py` (plans 003, 004).
- Shell scripts' colours (`bin/fzf-style.sh`, `bin/mux-usage.py`, `bin/mux-agents.sh`,
  `bin/mux-cwd.sh` also hold duplicated tables — deliberately deferred, see Maintenance).
- `kittymux.conf`, `kittymux-keys.conf.tpl`, `~/.config/kitty/*`.

## Git workflow

- Branch: `advisor/002-theme-tokens`
- Commit per step; style: lowercase area prefix (e.g. `theme: pure token module derived from kitty colours`).
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Create `python/kittymux_theme.py` with tests first

Write `tests/test_theme.py` (stdlib `unittest`, `sys.path.insert(0, "python")` at top)
covering: `blend` endpoints (`w=0 → bg`, `w=1 → fg`, `w=.5` midpoint on a known pair);
`contrast(0xffffff, 0x000000) == 21.0` (±0.01); `ensure_contrast` raises a
low-contrast pair (`0x3c3836` on `0x272727`) to `>= 3.0` and leaves a passing pair
unchanged; `dim(0x10a37f)` returns `0x095A46`-ish per-channel `int(c*0.55)`;
`parse_kitty_colors("background #272727\nforeground #ebdbb2\ncursor none\nbad line")`
→ `{"background": 0x272727, "foreground": 0xebdbb2}`; `from_colors` on the gruvbox
values (background `#272727`, foreground `#ebdbb2`, `color9 #fb4833`,
`color10 #b8ba25`, `color11 #fabc2e`, `color12 #83a597`, `color14 #8ec07b`,
`active_border_color #d3869b`) yields `accent == 0xd3869b`, `surface != bg`, and every
status colour has `contrast(x, bg) >= 3.0`; missing-keys input does not raise.
Then implement the module until tests pass.

**Verify**: `python3 -m unittest discover -s tests -v` → all tests pass (≥ 8 tests).

### Step 2: Create `python/kittymux_agents.py` with tests

`tests/test_agents.py`: `agent_in(["/usr/bin/node", "/home/u/.local/bin/claude"]) == "claude"`;
`agent_in(["zsh"]) is None`; every `AGENTS` brand is an int in `0..0xffffff`.

**Verify**: `python3 -m unittest discover -s tests -v` → all pass.

### Step 3: Wire `python/tab_bar.py`

1. At top (after stdlib imports), make the modules importable:

```python
import sys
for _d in (os.path.dirname(os.path.realpath(__file__)),
           os.environ.get("KITTY_CONFIG_DIRECTORY") or os.path.expanduser("~/.config/kitty")):
    if _d not in sys.path:
        sys.path.insert(0, _d)
import kittymux_agents, kittymux_theme
```

2. Delete the hardcoded colour constants and `_AGENT_GLYPHS/_AGENT_BRANDS/_AGENT_PROCS`;
   use `kittymux_agents.AGENTS`.
3. Add `_palette(draw_data)` that builds a `Palette` from the live options
   (`opts = get_options()`; `background`/`foreground`/`active_border_color`/
   `color1..color15` → raw ints via `int(color)`), **cached** on the tuple of input ints.
   **Verify how to read ANSI colours before coding it**: in the scratch instance
   (Step 6) temporarily write `dir(get_options())` filtered for `color` to
   `/tmp/kmx-opts.txt`; use whichever of `opts.color_table[n]` / `opts.colorN` exists.
   Remove the debug write afterwards. If neither exposes the ANSI palette, STOP.
4. Replace every use of the old constants with `as_rgb(pal.<token>)`:
   `_BG→bg`, `_SESSION_FG→info`, `_ACTIVE_FG→accent`, `_INACTIVE_FG→muted`,
   `_ACTIVITY_FG→done`, `_WAITING_FG→waiting`, `_SEP_FG→faint`, `_BRACKET_FG→faint`,
   `_CWD_FG→muted`, `_BRANCH_FG→done`, `_ALERT_FG→alert`. Use `kittymux_theme.dim`
   for inactive agent icons (`as_rgb(dim(brand))`, per plan 001's rule).
   Keep all layout logic untouched. Pass `pal` into helpers that need it
   (`_draw_cwd_anchor` gets it as a parameter).

**Verify**: `python3 -m py_compile python/tab_bar.py` → exit 0;
`grep -nE "0x[0-9a-f]{6}" python/tab_bar.py` → no palette literals remain
(only comments allowed).

### Step 4: Wire `python/sidebar-kit.py`

1. Same `sys.path` preamble but using only `KITTY_CONFIG_DIRECTORY`/`~/.config/kitty`
   (no `__file__` in kittens).
2. In `Sidebar.initialize`, fetch colours once via
   `kittymux_theme.parse_kitty_colors(_rc("get-colors", "--configured"))` →
   `from_colors` → module-level `PAL`; on empty output use `from_colors({})` fallback.
3. Replace `_MAUVE/_TEXT/_DIM/_FAINT/_ROW_BG/_EDGE/_SKY/_INDIGO/_EMERALD` with `Color`
   objects from `PAL` (keep `_C()` helper): `_MAUVE→accent`, `_TEXT→text`, `_DIM→muted`,
   `_FAINT→faint`, `_ROW_BG→surface_hi`, `_EDGE→faint`, `_SKY→working`,
   `_INDIGO→waiting`, `_EMERALD→done`. Replace `_GLYPHS/_BRANDS` with `kittymux_agents`.
   Layout untouched.

**Verify**: `python3 -m py_compile python/sidebar-kit.py` → exit 0;
`grep -nE "0x[0-9a-f]{6}" python/sidebar-kit.py` → none.

### Step 5: Install + docs

- `install.sh`: after the `tab_bar.py` symlink block, symlink
  `python/kittymux_theme.py` and `python/kittymux_agents.py` into `$KITTY_CONF_DIR`
  the same way (remove existing symlink, else back up a real file), plus `ok` lines.
  Update the header comment ("Symlinks python/*.py …").
- `AGENTS.md` Layout: add the two modules. `README.md` Layout tree: same.

**Verify**: `bash -n install.sh` → exit 0; `shellcheck -S warning install.sh` → only the two
pre-existing warnings (SC2034 `kitty_minor`, SC2174 `mkdir -p -m`).

### Step 6: Visual verification in a scratch kitty (never the user's live windows)

Run install-equivalent symlinks into a **temporary config dir**, not the real one:
`export KITTY_CONFIG_DIRECTORY=$(mktemp -d)`; copy the user's `kitty.conf` includes
minimally (`include /home/kitsunekode/.config/kitty/theme.conf`, then
`include $PWD/kittymux.conf`), symlink `tab_bar.py`, `kittymux_theme.py`,
`kittymux_agents.py` into it, then
`kitty --class kmx-t --config $KITTY_CONFIG_DIRECTORY/kitty.conf -o tab_bar_edge=left --listen-on unix:/tmp/kmx-t --session <a 4-tab session>`.
Screenshot with `grim -g` (if a display exists) and confirm: no Catppuccin navy —
bar colours now follow the theme (gruvbox); agent glyph colours correct; repeat with
another theme file (e.g. swap the `include` to a light theme) and confirm the bar
remains readable (contrast). Close it: `kitty @ --to unix:/tmp/kmx-t close-window --match all`.

**Verify**: screenshots reviewed; report headless limitation if no display.

## Test plan

- New: `tests/test_theme.py`, `tests/test_agents.py` (structure: plain
  `unittest.TestCase`, no fixtures; there is no existing test in this repo to mirror).
- `python3 -m unittest discover -s tests -v` → all pass.
- Visual check (Step 6) covers the kitty-only wiring, which cannot be unit-tested.

## Done criteria

- [ ] `python3 -m unittest discover -s tests` exits 0 with ≥ 10 tests
- [ ] `python3 -m py_compile python/*.py` exits 0
- [ ] `grep -nE "0x[0-9a-f]{6}" python/tab_bar.py python/sidebar-kit.py` shows no palette literals
- [ ] `grep -n "_AGENT_GLYPHS\|_GLYPHS = " python/tab_bar.py python/sidebar-kit.py` → no matches
- [ ] `bash -n install.sh` exits 0; installer symlinks the two new modules
- [ ] Only in-scope files modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

- The ANSI palette isn't reachable from `get_options()` (Step 3.3) or `get-colors`
  output doesn't parse as described (Step 4) — report what was found.
- `import kittymux_theme` fails under kitty's interpreter (path problem) — report the traceback from
  kitty's stderr; do not resort to copying the file into `tab_bar.py`.
- Any change would require editing an out-of-scope file.
- A visual check shows unreadable text (contrast < 3) on either dark or light theme.

## Maintenance notes

- Adding a provider: edit only `kittymux_agents.AGENTS` (+ the icon font via
  `tools/build-icons.py` if it has a brand mark).
- Still duplicated after this plan: agent tables/colours in `bin/mux-agents.sh`,
  `bin/mux-cwd.sh`, `bin/mux-usage.py`, `bin/fzf-style.sh`. Follow-up: have shell
  tools call a tiny `python -m kittymux_theme --shell` that prints `export` lines.
- Reviewer should scrutinise: `ensure_contrast` behaviour on light themes; whether
  `active_border_color` is a sensible accent for other themes (users can override
  with `KITTYMUX_ACCENT`); the sys.path preamble ordering.
- Plans 003/004 build on `Palette` tokens — do not rename tokens without updating them.
