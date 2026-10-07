# 008 — Remove dead code and stale artifacts (bar helper, install includes, template path, collector stat)

Small, independent cleanups found by audit. Grouped because each is a few lines; keep them as
separate commits so any one can be reverted.

## Item A — `_split_window_count` never fires (`python/tab_bar.py`)

`tab_bar.py` ~line 344:

```python
def _split_window_count(title: str) -> tuple[str, str]:
    if " :" in title and title.endswith(":"):
        prefix, suffix = title.rsplit(" :", 1)
        count = suffix[:-1]
        if count.isdigit():
            return prefix, f"+{count}"
    return title, ""
```

This only matches titles literally ending `":N:"` (e.g. `name :3:`). Verified against kitty
source 0.26.5 → 0.49.2 (`Tab.title`, `TabBarData`, `data_for_tab_bar`): kitty has never
appended ` :N` to tab titles, and nothing in kittymux produces that format either — the
function has been dead since v0.0.1 (`git log -S _split_window_count`). The pane count it was
meant to show is already drawn from `tab.num_windows` (~line 1132, `"{tab.num_windows}
panes"` subtitle). Call site at ~line 705 (`raw_title, window_count = _split_window_count(tab.title or "")`)
plus the `window_count` handling at ~line 740–742.

**Step:** delete `_split_window_count` and both usages; simplify the title truncation so the
limit no longer subtracts a never-present suffix. Verify no test asserts the `"+N"` suffix
(grep tests for `split_window_count` and `"+`).

## Item B — `include-tab-bar.conf` is created but never used (`install.sh`)

`install.sh` ~line 111–114 creates `$KITTY_CONF_DIR/include-tab-bar.conf` with the comment
"mux-bar.sh rewrites it" — but `bin/mux-bar.sh` does not exist, the file is **never** added to
`kitty.conf` (`add_include` is only called for the keys conf, the optional leader conf,
`kittymux.conf`, the edge file and the geninclude), and `kittymux.conf` line 6 already sets
`tab_bar_style custom`. Its only remaining references are `_MANAGED_FILES` in `bin/kittymux`
(uninstall cleanup) and `_NOT_OURS` in `python/kittymux_keymap.py`.

**Step:** delete the creation block from `install.sh`. Keep `include-tab-bar.conf` in
`_MANAGED_FILES`/`_NOT_OURS` so existing installs still clean it up. Fix the stale comment on
the edge-file block (~line 107): it says "mux-edge.sh rewrites it" — today `bin/mux-edge.sh`
delegates to `kittymux layout` which writes `layout-<pid>.json` state, not this file; the file
is only a pre-layout default read by `kittymux_layout.legacy_edge`.

## Item C — `/usr/bin/python3` in the keymap template (portability)

`kittymux-keys.conf.tpl` lines ~109 and ~172 run overlays as
`launch --type=overlay /usr/bin/python3 @KITTYMUX_HOME@/bin/mux-usage.py` (and `mux-keys.py`).
`/usr/bin/python3` does not exist on NixOS, some minimal images, and macOS. Both scripts have
`#!/usr/bin/env python3` shebangs and install.sh already `chmod +x`s `bin/*`, so the `python3`
prefix is only a safety net for a missing exec bit — use `python3` (PATH lookup) instead of
`/usr/bin/python3`. (Already listed as deferred debt in the previous README; still live.)

**Step:** edit the `.tpl` (never the rendered conf — AGENTS.md). After editing, re-render via
`install.sh` only in a scratch `KITTY_CONFIG_DIRECTORY`, per the smoke-test rules; and update
any key-table/doc line that quotes the command literally.

## Item D — claude collector: unguarded `stat` in sort key

`python/collectors/claude.py` ~line 27:

```python
files = sorted(root.rglob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
```

A file deleted between `rglob` and `stat` raises `OSError` inside `sorted` → the whole
`local()` fails → the provider row shows "error" instead of the other rows. Guard it:
`key=lambda p: p.stat().st_mtime if _exists(p) else 0` or wrap `p.stat()` in a small helper
returning `0` on `OSError` (files sort oldest-first is fine — the week_cut break then skips
them). Same pattern may exist in `codex.py`/`devin.py` — check and fix identically.

## Steps

1. One worktree (`.worktrees/cleanup`), four commits (A–D) so each is revertable.
2. After each commit run the relevant checks; at the end run the full list below.

## Acceptance criteria & verification

- `python3 -m unittest discover -s tests` passes.
- `bash tests/test_install.sh` passes (install/uninstall without `include-tab-bar.conf`).
- `python3 -m py_compile python/tab_bar.py python/collectors/*.py`; `bash -n install.sh`;
  `shellcheck -S error install.sh` clean.
- `git diff --check` clean; `python3 -m unittest tests.test_docs` passes if any doc line
  referenced the removed items.
- Grep: no remaining references to `_split_window_count`, `mux-bar.sh`; no `/usr/bin/python3`
  in `kittymux-keys.conf.tpl`.

## Risks / STOP conditions

- Do not remove `include-tab-edge.conf` handling — it is still read by
  `kittymux_layout.legacy_edge` for pre-layout installs.
- The key template is user-facing config: if `python3`-on-PATH fails for an existing user the
  overlay silently won't open. Keep the note in docs/README telling users overlays need
  `python3` on PATH; STOP if a reviewer prefers keeping the absolute path and documenting the
  requirement instead.
- Do not touch `~/.config/kitty` — render tests in a scratch dir only.

Effort: S · Priority: P2 · Files: `python/tab_bar.py`, `install.sh`, `kittymux-keys.conf.tpl`,
`python/collectors/{claude,codex,devin}.py`, possibly `tests/` + a doc line.
