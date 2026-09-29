# Plan 001: Fix inactive agent-icon colour and the broken cwd-HUD agent lookup

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md` — unless a reviewer dispatched you and told you they
> maintain the index.
>
> **Drift check (run first)**: `git diff --stat 8681a7d..HEAD -- python/tab_bar.py bin/mux-cwd.sh`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `8681a7d`, 2026-09-29

## Why this matters

Two small, independent, confirmed bugs. (1) In the tab bar, an *inactive* tab's
agent brand icon is drawn in a wrong colour (observed: codex's green logo
rendered blue) because a dimming helper mangles kitty's tagged colour ints.
(2) The `ctrl+alt+i` cwd HUD is supposed to peek at the agent running in the
host pane, but its Python snippet never receives the `kitty @ ls` JSON because a
heredoc replaces the pipe on its stdin — so agent/status detection silently
never works. Both are quick to fix and remove visible/invisible wrongness before
the larger UI work in plans 002–004.

## Current state

- `python/tab_bar.py` — kitty custom tab-bar drawer (loaded via `runpy` from
  `~/.config/kitty/tab_bar.py`, which is a symlink to this file). It runs inside
  kitty's bundled Python; `kitty.*` modules are importable there but NOT under
  system `python3`.
- Kitty's helper `as_rgb(x)` is defined in kitty as `(x << 8) | 2` — it returns a
  *tagged* colour int (low byte `0x02` = "RGB colour"). A value whose low byte is
  `0x01` is interpreted as a palette *index*, and `0x00` as "default".

Excerpts (`python/tab_bar.py`):

```python
def _dim(rgb: int, factor: float = 0.55) -> int:            # ~line 158
    r, g, b = (rgb >> 16) & 0xFF, (rgb >> 8) & 0xFF, rgb & 0xFF
    return (int(r * factor) << 16) | (int(g * factor) << 8) | int(b * factor)

def _agent_info(tab_id: int) -> tuple[str, int, str] | None:  # ~line 163
    """(glyph, brand_rgb, name) for the foreground agent CLI, else None."""
    ...
                rgb = _AGENT_BRANDS.get(name, 0x94e2d5)
                return _AGENT_GLYPHS.get(name, _AGENT_FALLBACK), as_rgb(rgb), name
```

and in `draw_tab` (~line 470):

```python
    if info:
        glyph, brand, _name = info
        screen.cursor.fg = brand if tab.is_active else _dim(brand)
        screen.draw(glyph)
```

The bug: `brand` is already `as_rgb(...)`-tagged (`0xRRGGBB02`), `_dim` then treats
it as plain `0xRRGGBB`, shifting channels, and returns an *untagged* int whose low
byte is `int(2*0.55) == 1` → kitty reads it as palette index 1. Active tabs look
right by accident (they pass the tagged int through untouched).

- `bin/mux-cwd.sh` lines ~95–131 — the "peek at the host pane" block:

```bash
        mapfile -t hi < <(kitty @ --to "$to" ls 2>/dev/null | python3 - <<'PY'
import json, os, sys
...
    data = json.load(sys.stdin)
...
PY
)
```

`python3 -` reads the *program* from stdin; the heredoc (`<<'PY'`) overrides the
pipe, so `sys.stdin` is the script itself, `json.load` fails, the script exits
silently, and `host_id`/`agent` stay empty. `shellcheck` reports this as
`SC2259 (error)` at `bin/mux-cwd.sh:99`.

Conventions: shell scripts use `set -u`-style bash with 4-space indent; Python in
this repo is plain, typed-lightly, no formatter config. Match surrounding style.
Verification conventions from `AGENTS.md`: `python3 -m py_compile` on touched
python, `bash -n` on shell.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Python syntax | `python3 -m py_compile python/tab_bar.py` | exit 0 |
| Shell syntax | `bash -n bin/mux-cwd.sh` | exit 0 |
| Shellcheck errors only | `shellcheck -S error bin/mux-cwd.sh` | exit 0, no output |
| Scratch kitty (UI test) | see Step 3 | window renders |

## Scope

**In scope**:
- `python/tab_bar.py`
- `bin/mux-cwd.sh`

**Out of scope** (do NOT touch):
- Any other colour/palette change in `tab_bar.py` — plan 002 owns the palette rework.
- `python/sidebar-kit.py` — it uses `Color` objects and is not affected.
- `~/.config/kitty/*` — the user's live config; never edit.

## Git workflow

- Branch: `advisor/001-fix-icon-color-and-cwd-heredoc`
- Commit per step; message style matches the repo (`git log`): lowercase
  area prefix, e.g. `tab bar: dim agent icons via raw rgb, then tag once`.
- Do NOT push or open a PR unless the operator instructed it.

## Steps

### Step 1: Make `_agent_info` return the *raw* hex and tag exactly once at draw time

In `python/tab_bar.py`:
1. In `_agent_info`, return the raw int: replace `as_rgb(rgb)` with `rgb` in the
   return statement, and update its docstring/tuple comment to say `brand_rgb`
   is a plain `0xRRGGBB` int.
2. In `draw_tab`, replace the icon colour line with:

```python
        screen.cursor.fg = as_rgb(brand if tab.is_active else _dim(brand))
```

(`_dim` is unchanged and correct for plain `0xRRGGBB` input.)

**Verify**: `python3 -m py_compile python/tab_bar.py` → exit 0;
`grep -n "as_rgb(rgb)" python/tab_bar.py` → no match inside `_agent_info`.

### Step 2: Fix the stdin/heredoc collision in `bin/mux-cwd.sh`

Pass the Python program with `-c` so stdin stays free for the pipe. Replace the
`mapfile -t hi < <(kitty @ ... | python3 - <<'PY' ... PY\n)` construct with:

```bash
        hi_py=$(cat <<'PY'
<the exact existing Python body, unchanged>
PY
)
        mapfile -t hi < <(kitty @ --to "$to" ls 2>/dev/null | python3 -c "$hi_py")
```

Keep the Python body byte-for-byte the same (it already reads `sys.stdin`).
Do not alter the second python block (`st=$(python3 - "$host_id" ... <<'PY'`) —
it has no pipe and is correct.

**Verify**:
- `bash -n bin/mux-cwd.sh` → exit 0
- `shellcheck -S error bin/mux-cwd.sh` → exit 0, no `SC2259`

### Step 3: Behavioural check in a scratch kitty (never the user's live windows)

```sh
S=$(mktemp -d)
cat > $S/sess.kitty <<EOF
new_tab a
launch sh -c 'exec -a codex sleep 600'
new_tab b
launch
EOF
kitty --class kmx-t --listen-on unix:/tmp/kmx-t --session $S/sess.kitty &
sleep 2
```

(a) cwd-HUD lookup: with tab `b` active and a `codex`-named process in the
*same* tab, run the extracted snippet manually:
`kitty @ --to unix:/tmp/kmx-t ls | python3 -c "$hi_py"` after copying the body —
or simply run `KITTY_LISTEN_ON=unix:/tmp/kmx-t bin/mux-cwd.sh` inside a pane of
that instance and confirm the card shows the agent line. **Expected**: the HUD
lists the agent name (`codex`) instead of the empty host line.

(b) icon colour (needs a display; skip and note "not visually verified" if headless):
focus tab `b` so tab `a` is inactive; `grim -g "<x>,<y> <w>x<h>" /tmp/kmx-t.png` of
the window and confirm the codex glyph in the inactive row is a *dimmed green*,
not blue. Close the scratch window: `kitty @ --to unix:/tmp/kmx-t close-window --match all`.

**Verify**: as described; report what was and wasn't visually verified.

## Test plan

No automated tests exist in this repo and `tab_bar.py` cannot be imported outside
kitty, so verification is the gates above plus the scratch-instance check. Do not
add a test framework in this plan (see plan 002, which introduces pure-Python
modules that *are* unit-testable).

## Done criteria

- [ ] `python3 -m py_compile python/tab_bar.py` exits 0
- [ ] `bash -n bin/mux-cwd.sh` exits 0
- [ ] `shellcheck -S error bin/mux-cwd.sh` exits 0
- [ ] `grep -n "_dim(brand)" python/tab_bar.py` shows the call wrapped in `as_rgb(...)`
- [ ] Only `python/tab_bar.py` and `bin/mux-cwd.sh` modified (`git status`)
- [ ] `plans/README.md` status row updated

## STOP conditions

- The excerpts don't match live code (drift).
- `kitty @ ls` output no longer contains `foreground_processes` per window
  (then the heredoc fix would not be sufficient — report the JSON shape).
- The dimmed icon is still not green after Step 1 (then the cause is elsewhere,
  e.g. the icon font's symbol_map — report, don't guess).
- Fixing requires editing anything outside the two in-scope files.

## Maintenance notes

- Rule of thumb for this codebase: kitty `screen.cursor.fg/bg` want *tagged* ints
  (`as_rgb`); do arithmetic on raw `0xRRGGBB` and tag once at the draw call.
  Plan 002 centralises this in a `theme` module — keep it consistent.
- The same "peek at host pane" agent-name table is duplicated in several files;
  plan 002 dedupes the Python copies.
