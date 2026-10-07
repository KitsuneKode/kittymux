# UI design system and panel views: implementation plan

Spec: `docs/superpowers/specs/2026-10-07-ui-design-system-design.md`. Branch `ui-system` in `.worktrees/ui-system`. Plan 007 (journal stale
open records) was found already fixed on `main` and covered by `test_agent_exit_in_a_live_window_closes_its_journal_record`; nothing to do.

Each task: failing test first, then the code, then `python3 -m unittest discover -s tests` and `py_compile`. Commit per task.

1. **Theme tokens.** `Palette` gains `card`, `card_hi`, `track`, `on_accent`; `from_colors` fills them (live colours only). Tests: tokens differ
   from each other and from `bar`, `ensure_contrast` >= 4.5 for text on `card` in a dark and a light palette.
2. **`kittymux_ui.py`.** Spans and components: `pad`, `chip`, `tabs`, `gauge`, `kv`, `card`, `keycaps`, `spark`, `bars`, `heat`, `tile`.
   Tests: every line is exactly `width` cells (also with wide characters), no component raises on width 0 or 1, hostile text is cleaned,
   gauge fill is monotonic in pct, the pace tick lands where asked, card corners are the quadrant glyphs.
3. **`kittymux_meters.py`.** `meters(provider, now, history)` -> list of `quota|counter|state|spend` dicts, from structured sidecar fields when
   present and from the row's label and text when not (old caches keep working). Tests per provider shape, junk input, NaN, bool, negative.
4. **Collector sidecars.** Codex, Claude, Cursor, Devin rows gain `rem_s`, `window_s`, `tok`, `cached`, `sess`, `ago_s`, `state` without changing
   `text` / `reset`. `tests/test_collectors.py` pins both.
5. **Usage view.** `kittymux_usageview.view(data, history, cols, rows, sel, p, cells)` returns lines plus hit regions (provider tiles). The
   sidebar kit draws them; keys: left/right (or h/l) pick a provider, up/down scroll, `r` refresh. A live-quotas switch is not added: opt-in
   stays an environment or flag-file decision. Mouse: click a tile selects it.
6. **Inbox view.** `kittymux_inboxview.view(events, filter, sel, ...)`: filter chips (All, Needs you, Done, Limits), typed cards, Jump (Enter)
   runs `kittymux inbox jump`, `x` dismisses (`inbox ack`). Empty and quiet states.
7. **Tab strip.** Three icon tabs (Agents, Usage, Inbox with badge); keys `a`, `u`, `i`; clicking an icon switches view.
8. **Screenshot rig.** `tests/shot_panel.sh dark|light OUT [view] [cols]` runs the real panel in an isolated Xvfb kitty with synthetic data;
   read the PNGs, fix what looks wrong.
9. **Docs.** `docs/users/` panel page, `feature-status.yaml`, README panel section, CHANGELOG; `tests/test_docs.py` stays green.
10. **Demo.** A rendered set of real panel screenshots (Usage dark/light, Counter provider, Inbox, narrow) for the review canvas.

Stretch, only after 1 to 10 are verified: workspace switcher plus session rename (`feature-status.yaml` planned items), command palette.
