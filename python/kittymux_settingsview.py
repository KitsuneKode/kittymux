"""The panel's Settings view (pure): the switch catalog (kittymux_switches) in, styled lines and click regions out.

One row per switch, grouped. A row says its state in a glyph AND a word (never colour alone) and, when the value is not the default, where it comes from (`env`,
`file`). The picked row opens: what it does in a sentence, and, for a switch held by your environment, which variable holds it (such a row is locked: kittymux never
edits your shell). A risky switch asks before it turns ON: the consequence in two lines and two buttons; turning anything OFF never asks.

Nothing here writes a file or runs anything: the caller (sidebar-kit) owns keys, mouse and the state directory. Text from the catalog and from the environment is
`kittymux_place.clean`ed and bounded before it is drawn."""
from __future__ import annotations

from typing import NamedTuple

import kittymux_deck
import kittymux_features as F
import kittymux_place
import kittymux_switches as SW
import kittymux_ui as U

PRESET_NAMES = tuple(F.PRESETS)
SHORT_PRESET = {"minimal": "min", "default": "std", "full": "all"}


class Row(NamedTuple):
    sw: SW.Switch
    on: bool
    where: str          # 'env' | 'flag' | 'default'
    what: str           # the variable or file that decided it


class SettingsView(NamedTuple):
    header: list
    lines: list            # the body under the tab strip
    rows: list             # [(y0, y1, id)] body coordinates: the whole picked or unpicked row (and its detail lines)
    toggles: list          # [(x0, x1, y, id)] the state pill of each row
    presets: list          # [(x0, x1, y, preset)] the preset chips
    buttons: list          # [(x0, x1, y, action)] confirm / cancel while a risky switch is asking
    sel: int
    count: int
    ids: list              # the ids in the order `sel` indexes


def rows(sdir: str | None = None, env=None) -> list[Row]:
    """Every switch with its current state, in catalog order grouped as the view shows them."""
    out = []
    for _, group in SW.by_group():
        for sw in group:
            on, where, what = SW.resolve(sw.id, sdir, env)
            out.append(Row(sw, on, where, what))
    return out


def ids_in_order() -> list[str]:
    return [sw.id for _, group in SW.by_group() for sw in group]


def locked(row: Row) -> bool:
    """Held by the environment: the panel cannot change it (and will not touch your shell)."""
    return row.where == "env"


def changed(rows_: list[Row]) -> int:
    return sum(1 for r in rows_ if r.on != r.sw.default or r.where == "env")


def current_preset(rows_: list[Row]) -> str | None:
    """The preset the twelve classic switches match right now, or None. The presets only concern those twelve."""
    state = {r.sw.id: r.on for r in rows_ if r.sw.id in F.FEATURES}
    for name, members in F.PRESETS.items():
        if all(state.get(f) == (f in members) for f in F.FEATURES):
            return name
    return None


def needs_confirm(row: Row) -> bool:
    """A risky switch asks before it turns ON. Turning it off, or anything harmless either way, never asks."""
    return row.sw.risk != SW.NONE and not row.on and not locked(row)


def _wrap(kit: U.Kit, text: str, width: int, rows_: int) -> list:
    if width <= 0 or rows_ <= 0:
        return []
    lines, cur, cut = [], "", False
    for word in kittymux_place.clean(text).split():
        word = kittymux_deck.fit(word, width, kit.cells)
        cand = (cur + " " + word).strip()
        if kit.cells(cand) <= width:
            cur = cand
            continue
        lines.append(cur)
        cur = word
        if len(lines) == rows_:
            cut, cur = True, ""
            break
    if cur:
        lines.append(cur)
    if cut and lines:
        lines[-1] = kittymux_deck.fit(lines[-1] + "…", width, kit.cells)
    return lines[:rows_]


def _state_pill(kit: U.Kit, row: Row, bg: int) -> list:
    p = kit.p
    word = "on " if row.on else "off"                  # the same 5 cells either way: the state is a click target and must not shift when it flips
    glyph = "●" if row.on else "○"
    dim = locked(row) or row.sw.status == SW.PLANNED
    color = p.done if row.on else p.muted
    return [U.S(f"{glyph} ", kit.ink(color, bg), bg, bold=not dim), U.S(word, kit.ink(p.text if row.on else p.muted, bg), bg, bold=row.on and not dim, dim=dim)]


def _source(kit: U.Kit, row: Row, bg: int) -> list:
    """`env` / `file` after the state, only when the value is not the default's own: the quiet default look stays quiet."""
    p = kit.p
    if row.where == "env":
        return [U.S("env ", kit.ink(p.waiting, bg), bg, bold=True)]
    if row.where == "flag":
        return [U.S("file ", kit.ink(p.muted, bg), bg)]
    return []


def _switch_rows(kit: U.Kit, row: Row, inner: int, selected: bool, asking: bool, notice) -> tuple:
    """Returns (lines, pill_x0, pill_x1, button_row or None, [(x0, x1, action)])."""
    p = kit.p
    bg = p.card_hi if selected else p.bar
    planned = row.sw.status == SW.PLANNED
    pill = _state_pill(kit, row, bg)
    src = _source(kit, row, bg) if inner >= 30 else []
    right = src + pill + [U.S(" ", None, bg)]         # the state is the LAST thing on the row: it never moves when `env` / `file` appears, so a second click lands on it again
    right_w = U.line_cells(right, kit.cells)
    mark = "▸ " if selected else "  "
    label_w = max(1, inner - right_w - 3)                      # 2 for the marker, 1 for air between the name and its state
    label = kittymux_deck.fit(kittymux_place.clean(row.sw.label) + (" (planned)" if planned and inner >= 34 else ""), label_w, kit.cells)
    left = [U.S(mark, kit.ink(p.accent, bg), bg, bold=True), U.S(label, kit.ink(p.muted if planned else p.text, bg), bg, bold=selected, dim=planned)]
    gap = max(0, inner - U.line_cells(left, kit.cells) - right_w)
    line = kit.fit_line(left + [U.S(" " * gap, None, bg)] + right, inner, bg)
    pill_w = U.line_cells(pill, kit.cells)
    pill_x0 = inner - 1 - pill_w
    pill_x1 = pill_x0 + pill_w
    out = [line]
    buttons, button_row = [], None
    if selected:
        detail_w = max(1, inner - 2)
        for text in _wrap(kit, row.sw.help, detail_w, 2):
            out.append(kit.fit_line([U.S("  " + text, kit.ink(p.muted, bg), bg)], inner, bg))
        if locked(row):
            for t in _wrap(kit, f"held by {row.what} in your environment: unset it to change this", detail_w, 2):
                out.append(kit.fit_line([U.S("  " + t, kit.ink(p.waiting, bg), bg)], inner, bg))
        elif planned:
            out.append(kit.fit_line([U.S("  not built yet: saved for when it exists", kit.ink(p.faint, bg, 3.0), bg)], inner, bg))
        elif asking:
            for text in _wrap(kit, row.sw.consequence, detail_w, 4):
                out.append(kit.fit_line([U.S("  " + text, kit.ink(p.waiting, bg), bg)], inner, bg))
            tiers = [[("confirm", kit.button("Turn on", "⏎", primary=True, on=bg)), ("cancel", kit.button("Cancel", "esc", on=bg))],
                     [("confirm", kit.button("Turn on", primary=True, on=bg)), ("cancel", kit.button("Cancel", on=bg))],
                     [("confirm", kit.button("On", primary=True, on=bg)), ("cancel", kit.button("✕", on=bg))]]
            for tier in tiers:
                widths = [U.line_cells(b, kit.cells) for _, b in tier]
                if 2 + sum(widths) + len(tier) - 1 <= inner:
                    line2, x = [U.S("  ", None, bg)], 2
                    for (action, button), w in zip(tier, widths):
                        if len(line2) > 1:
                            line2.append(U.S(" ", None, bg))
                            x += 1
                        line2 += button
                        buttons.append((x, x + w, action))
                        x += w
                    out.append(kit.fit_line(line2, inner, bg))
                    button_row = len(out) - 1
                    break
        if notice and notice[0] == row.sw.id:
            tone = kit.ink(p.alert if notice[2] == "error" else p.done, bg)
            out += [kit.fit_line([U.S("  " + t, tone, bg)], inner, bg) for t in _wrap(kit, notice[1], detail_w, 2)]
    return out, pill_x0, pill_x1, button_row, buttons


def _presets(kit: U.Kit, current: str | None, cols: int) -> tuple:
    """The three presets on one row. The widest wording that fits wins: `Preset minimal default full`, the three names, short names, one letter each. All three stay
    clickable at any width a person would use."""
    p = kit.p
    words = {n: n for n in PRESET_NAMES}
    short = dict(SHORT_PRESET)
    letters = {n: n[0] for n in PRESET_NAMES}
    tiers = [("Preset", words), ("", words), ("", short), ("", letters)]
    for i, (lead, names_) in enumerate(tiers):
        names = [(n, names_[n]) for n in PRESET_NAMES]
        label = [U.S(f" {lead} ", kit.ink(p.muted, p.bar), p.bar)] if lead else [U.S(" ", None, p.bar)]
        width = U.line_cells(label, kit.cells) + sum(kit.chip_width(t) for _, t in names) + len(names) - 1
        if width <= cols or i == len(tiers) - 1:
            line, regions, x = list(label), [], U.line_cells(label, kit.cells)
            for n, t in names:
                active = n == current
                chip = kit.chip(t, "text" if active else "muted", on=p.bar, strong=active)
                w = U.line_cells(chip, kit.cells)
                if x + w > cols:
                    break
                line += chip + [U.S(" ", None, p.bar)]
                regions.append((x, x + w, n))
                x += w + 1
            return kit.fit_line(line, cols, p.bar), regions
    return kit.blank(cols, p.bar), []


def view(rows_: list[Row], sel: int, cols: int, kit: U.Kit, asking: str | None = None, notice=None) -> SettingsView:
    """Never raises. `sel` indexes `ids_in_order()` (clamped). `asking` is the id of a risky switch waiting for its confirmation; `notice` is (id, text, 'ok'|'error')
    shown under that row. All regions are in body coordinates (the line under the tab strip is y = 0)."""
    p = kit.p
    cols = max(8, int(cols))
    ids = [r.sw.id for r in rows_]
    by_id = {r.sw.id: r for r in rows_}
    sel = max(0, min(int(sel) if isinstance(sel, (int, float)) else 0, max(0, len(ids) - 1)))
    n = changed(rows_)
    left = [U.S(f" {n} changed" if n else " all defaults", kit.ink(p.muted, p.bar), p.bar)]
    held = sum(1 for r in rows_ if locked(r))
    if held:
        left.append(U.S(f"  {held} held by env", kit.ink(p.waiting, p.bar), p.bar, bold=True))
    header = kit.fit_line(left, cols, p.bar)
    preset_line, preset_regions = _presets(kit, current_preset(rows_), cols)
    lines = [preset_line]
    presets = [(x0, x1, 0, name) for x0, x1, name in preset_regions]
    row_regions, toggles, buttons = [], [], []
    inner = max(4, cols - 2)
    for gname, group in SW.by_group():
        lines.append(kit.blank(cols, p.bar))
        lines.append(kit.fit_line([U.S(" " + gname.upper(), kit.ink(p.faint, p.bar, 3.0), p.bar, bold=True)], cols, p.bar))
        for sw in group:
            row = by_id.get(sw.id)
            if row is None:
                continue
            i = ids.index(sw.id)
            selected = i == sel
            body, px0, px1, brow, regions = _switch_rows(kit, row, inner, selected, asking == sw.id, notice)
            y0 = len(lines)
            for part in body:
                lines.append([U.S(" ", None, p.card_hi if selected else p.bar)] + part + [U.S(" ", None, p.card_hi if selected else p.bar)])
            row_regions.append((y0, len(lines), sw.id))
            toggles.append((1 + px0, 1 + px1, y0, sw.id))
            if brow is not None:
                buttons += [(1 + a, 1 + b, y0 + brow, act) for a, b, act in regions]
    return SettingsView(header, lines, row_regions, toggles, presets, buttons, sel, len(ids), ids)
