"""The panel's `?` card (pure): the keys and mouse gestures of the view you are in, in the panel itself.

Not the global keymap overlay (`ctrl+alt+/`): that opens in a kitty window, which is the wrong place when the panel is docked on the screen edge.
The list is data here so a test can check every key it names is one the panel handles."""
from __future__ import annotations

import kittymux_deck
import kittymux_place
import kittymux_ui as U

# (keys as shown, what they do): keys are the tokens the panel's on_key_event understands, joined for reading
KEYS = {
    "agents": [
        ("j k", "move down / up"), ("⏎", "go to the tab (the pane that asks)"), ("/", "find a tab"), ("→ ← o", "open / close a split's panes"),
        ("a", "pull this tab's panes into yours"), ("t", "turn the pane into its own tab"), ("J K", "next / previous session"), ("g G", "first / last"),
        ("u i s", "Usage / Inbox / Settings"), ("q", "quit the panel"),
    ],
    "usage": [
        ("← →", "pick a provider"), ("1-9", "pick by number"), ("r", "refresh now"), ("d", "details and sources"), ("↑ ↓", "scroll"),
        ("a i s", "Agents / Inbox / Settings"), ("q", "quit the panel"),
    ],
    "inbox": [
        ("j k", "move down / up"), ("⏎", "go to the agent"), ("x X", "dismiss this / all in the filter"), ("z", "undo the last dismissal"),
        ("tab 1-4", "change the filter"), ("g G", "first / last"), ("r", "reload"), ("a u s", "Agents / Usage / Settings"), ("q", "quit the panel"),
    ],
    "settings": [
        ("j k", "move down / up"), ("space ⏎", "turn it on or off"), ("p P", "next / previous preset"), ("r R", "reset this one / its whole group"),
        ("g G", "first / last"), ("esc a", "back to Agents"), ("u i", "Usage / Inbox"), ("q", "quit the panel"),
    ],
}
MOUSE = {
    "agents": [("hover", "preview a tab or pane"), ("click", "go to it"), ("▸ ▾", "open / close a split's panes"), ("drag edge", "resize the panel")],
    "usage": [("click a tile", "pick that provider")],
    "inbox": [("click a card", "pick it"), ("Jump / Dismiss", "act on the picked card"), ("a chip", "filter")],
    "settings": [("a row", "pick it"), ("a state", "turn it on or off"), ("a preset", "apply it"), ("a button", "answer the question")],
}
TITLES = {"agents": "Agents", "usage": "Usage", "inbox": "Inbox", "settings": "Settings"}


def view(name: str, cols: int, kit: U.Kit) -> list:
    """Lines (each exactly `cols` wide) for the help card of view `name`; an unknown name gets the Agents card."""
    p = kit.p
    name = name if name in KEYS else "agents"
    cols = max(8, int(cols))
    inner = kit.inner_width(cols)
    bg = p.card
    rows: list = [kit.fit_line([U.S(f"{TITLES[name]} keys", kit.ink(p.text, bg), bg, bold=True)], inner, bg), kit.blank(inner, bg)]
    for group in (KEYS[name], MOUSE[name]):
        keyw = max(U.line_cells([U.S(kittymux_place.clean(k))], kit.cells) for k, _ in group)       # one cap width per group: the descriptions line up
        capw = keyw + 2
        for keys, text in group:
            pad = keyw - U.line_cells([U.S(kittymux_place.clean(keys))], kit.cells)
            cap = U.S(f" {kittymux_place.clean(keys)}{' ' * pad} ", kit.ink(p.text, p.card_hi), p.card_hi, bold=True)
            room = max(1, inner - capw - 1)
            lines = kittymux_deck.wrap_words(text, room, kit.cells) or [""]
            for i, chunk in enumerate(lines[:3]):
                lead = [cap] if i == 0 else [U.S(" " * capw, None, bg)]
                rows.append(kit.fit_line(lead + [U.S(" " + chunk, kit.ink(p.muted, bg), bg)], inner, bg))
        rows.append(kit.blank(inner, bg))
    rows.append(kit.fit_line([U.S("? or esc closes this", kit.ink(p.faint, bg, 3.0), bg)], inner, bg))
    return [kit.blank(cols, p.bar)] + kit.card(rows, cols)
