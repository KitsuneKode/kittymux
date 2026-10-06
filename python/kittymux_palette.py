"""The command palette (pure): one searchable list of everything you can go to or do, drawn with the shared kit.

Sources, in the order the list shows them:
  Needs you   unread attention events that ask for you (`pick` rows of kind `event`, urgent)      → jump to the agent
  Inbox       the other unread events (finished runs, limits)                                      → jump to the agent
  Tabs        every tab of this kitty with its state and folder                                    → focus the tab
  Agents      conversations you closed (reopen) and a new agent per installed CLI (spawn)         → `kittymux act`
  Actions     a short fixed list (join, quiet popups, the panel, …)                                → `kittymux act`

Every item carries ONE `action` dict. The kitten hands it to `kittymux act`, which re-validates it (`validate_action`): the palette only ever asks
for things on a whitelist, with ids and names shaped like ids and names. Text from tabs, agents and events is untrusted and is cleaned before it
is drawn. Nothing here talks to kitty or reads a file."""
from __future__ import annotations

import re
from typing import NamedTuple

import kittymux_agents
import kittymux_place
import kittymux_ui as U
import kittymux_usageview as V

GROUPS = ("Needs you", "Inbox", "Tabs", "Agents", "Actions")
TITLE_MAX = 160

# Fixed actions: id -> (title, hint, kittymux argv). `act` runs exactly these argvs and nothing else.
ACTIONS = {
    "join": ("Join this tab into another", "ctrl+alt+shift+j", ["join"]),
    "peek": ("Quick look at the agent that has waited longest", "ctrl+alt+shift+q", ["peek", "--waiting"]),
    "panel": ("Show or hide the docked panel", "ctrl+alt+shift+b", ["panel", "toggle"]),
    "mute": ("Quiet popups and bells for an hour (the inbox keeps everything)", "", ["notify", "mute", "1h"]),
    "unmute": ("Bring popups and bells back", "", ["notify", "unmute"]),
    "save": ("Save this session with its agent conversations", "", ["sessions", "save"]),
}

_ID = re.compile(r"[0-9a-fA-F-]{1,64}")
_KEY = re.compile(r"[a-z][a-z0-9-]{0,23}:[A-Za-z0-9][A-Za-z0-9._-]{0,127}")        # a journal key: agent:session-id or agent:w<pid>.<window>
_AGENT = re.compile(r"[a-z][a-z0-9-]{0,23}")
_WHERE = ("tab", "vsplit", "hsplit")


def _text(value, limit: int = TITLE_MAX) -> str:
    return kittymux_place.clean(str(value if value is not None else ""))[:limit]


def _item(group: str, title: str, detail: str = "", mark: tuple = ("·", "muted"), agent: str = "", right: str = "", action: dict | None = None) -> dict:
    return {"group": group, "title": _text(title), "detail": _text(detail, 100), "mark": mark, "agent": _text(agent, 24).lower(), "right": _text(right, 24),
            "action": action or {}}


def from_tabs(tabs) -> list:
    """tabs: [{os, id, title, cwd, panes, state}] (what the kitten reads from `kitty @ ls`)."""
    out = []
    for t in tabs if isinstance(tabs, list) else []:
        if not isinstance(t, dict) or not isinstance(t.get("id"), int) or isinstance(t.get("id"), bool):
            continue
        state = t.get("state") if t.get("state") in ("waiting", "limited", "working", "done") else ""
        tone = {"waiting": "warm", "limited": "hot", "working": "calm", "done": "calm"}.get(state, "muted")
        glyph = kittymux_agents.state_glyph(state) if state else "▸"
        n = t.get("panes") if isinstance(t.get("panes"), int) and not isinstance(t.get("panes"), bool) else 1
        cwd = _text(t.get("cwd"), 80)
        out.append(_item("Tabs", t.get("title") or "tab", cwd.rsplit("/", 1)[-1] if cwd else "", (glyph or "▸", tone), "", f"{n} panes" if n > 1 else "",
                         {"op": "focus-tab", "tab": t["id"]}))
    return out


def from_rows(rows) -> list:
    """`kittymux pick --json` rows. Running agents are skipped: they already are tabs, with their state."""
    out = []
    for r in rows if isinstance(rows, list) else []:
        if not isinstance(r, dict) or not isinstance(r.get("action"), dict):
            continue
        a, kind = r["action"], r.get("kind")
        raw = kittymux_place.clean_line(str(r.get("text") if r.get("text") is not None else ""))
        body = raw[3:] if len(raw) > 3 and raw[1:3] == "  " else raw                     # the row's own leading glyph is replaced by our mark
        agent = _text(r.get("agent"), 24).lower()
        if kind == "event":
            urgent = r.get("tone") == "urgent"
            out.append(_item("Needs you" if urgent else "Inbox", body, "", ("!", "warm") if urgent else ("✓", "calm"), agent, "", dict(a)))
        elif kind == "closed":
            out.append(_item("Agents", body, "", ("↺", "muted"), agent, "reopen", dict(a)))
        elif kind == "new":
            out.append(_item("Agents", body, "", ("+", "accent"), agent, "", dict(a)))
        elif kind == "utility" and a.get("op") == "usage":
            out.append(_item("Actions", "Open the usage overlay", "", ("◔", "muted"), "", "", dict(a)))
    return out


def actions() -> list:
    return [_item("Actions", title, "", ("▸", "muted"), "", hint, {"op": "run", "id": key}) for key, (title, hint, _argv) in ACTIONS.items()]


def build(tabs, rows) -> list:
    items = from_rows(rows) + from_tabs(tabs) + actions()
    order = {g: i for i, g in enumerate(GROUPS)}
    return sorted(items, key=lambda it: order[it["group"]])             # sorted() is stable: each group keeps its own order


# ── matching ──────────────────────────────────────────────────────────────────
def _haystack(it: dict) -> str:
    return " ".join((it["title"], it["detail"], it["agent"], it["group"], it["right"])).lower()


def score(query: str, it: dict):
    """None when some word of the query is nowhere in the item; else a number, lower = better: a word that starts the title or any word beats
    one buried in the middle, and the title beats the details."""
    words = query.lower().split()
    if not words:
        return 0
    hay, title = _haystack(it), it["title"].lower()
    total = 0
    for w in words:
        i = hay.find(w)
        if i < 0:
            return None
        if title.startswith(w):
            total += 0
        elif f" {w}" in f" {title}":
            total += 1
        elif w in title:
            total += 2
        else:
            total += 3
    return total


def filter_items(items: list, query: str) -> list:
    """No query: the grouped list as built. A query: one flat list, best match first (ties keep the grouped order)."""
    q = (query or "").strip()
    if not q:
        return list(items)
    scored = [(s, i, it) for i, it in enumerate(items) if (s := score(q, it)) is not None]
    return [it for _s, _i, it in sorted(scored, key=lambda x: (x[0], x[1]))]


class Cursor:
    """The query and the picked row, with the keys' semantics (the kitten maps keys to these)."""

    def __init__(self):
        self.query, self.index, self.count = "", 0, 0

    def type(self, text: str) -> None:
        self.query += "".join(ch for ch in text if ch.isprintable())[:200]
        self.query = self.query[:200]
        self.index = 0

    def backspace(self) -> None:
        self.query = self.query[:-1]
        self.index = 0

    def clear(self) -> None:
        self.query, self.index = "", 0

    def move(self, delta: int) -> None:
        self.index = max(0, min(self.index + delta, max(0, self.count - 1)))


# ── the one door in: what `kittymux act` accepts ──────────────────────────────
def validate_action(obj, known_agents=()) -> dict | None:
    """A copy of `obj` shaped as one of the palette's actions, or None. `known_agents`: the agent names `spawn` may start."""
    if not isinstance(obj, dict):
        return None
    op = obj.get("op")
    num = lambda v: isinstance(v, int) and not isinstance(v, bool) and 0 <= v < 2 ** 40          # noqa: E731
    if op == "focus-tab" and num(obj.get("tab")):
        return {"op": op, "tab": obj["tab"]}
    if op == "jump" and num(obj.get("pid")) and str(obj.get("w", "")).isdigit():
        out = {"op": op, "pid": obj["pid"], "w": str(obj["w"])}
        if isinstance(obj.get("ack"), str) and _ID.fullmatch(obj["ack"]):
            out["ack"] = obj["ack"]
        return out
    if op == "reopen" and isinstance(obj.get("key"), str) and _KEY.fullmatch(obj["key"]) and ".." not in obj["key"]:
        return {"op": op, "key": obj["key"]}
    if op == "spawn" and isinstance(obj.get("agent"), str) and _AGENT.fullmatch(obj["agent"]) and obj.get("where") in _WHERE:
        if known_agents and obj["agent"] not in known_agents:
            return None
        return {"op": op, "agent": obj["agent"], "where": obj["where"]}
    if op == "run" and isinstance(obj.get("id"), str) and obj["id"] in ACTIONS:
        return {"op": op, "id": obj["id"]}
    if op == "usage":
        return {"op": op}
    return None


# ── the view ──────────────────────────────────────────────────────────────────
class PaletteView(NamedTuple):
    lines: list            # the list region, one Line per row, each exactly `cols` wide
    hits: list             # [(y, index into the filtered items)] for the item rows
    preview: list          # up to PREVIEW_ROWS lines about the picked item
    scroll: int
    count: int


PREVIEW_ROWS = 3


def _mark(kit: U.Kit, it: dict, bg: int) -> list:
    glyph, tone = it["mark"]
    if it["agent"] and it["agent"] in kittymux_agents.AGENTS and it["group"] in ("Agents", "Needs you", "Inbox"):
        return V.mark(it["agent"], kit, bg)
    return kit.monogram(glyph, kit.tone(tone), bg)


def _row(kit: U.Kit, it: dict, selected: bool, cols: int) -> list:
    p = kit.p
    bg = p.card_hi if selected else p.bar
    left = [U.S("▌" if selected else " ", p.accent if selected else None, bg)] + _mark(kit, it, bg) + [U.S(" ", None, bg)]
    title = [U.S(it["title"], kit.ink(p.text if selected else p.muted if it["group"] == "Actions" else p.text, bg), bg, bold=selected)]
    if it["detail"]:
        title.append(U.S("  " + it["detail"], kit.ink(p.faint, bg, 3.0), bg))
    right = [U.S(it["right"] + " ", kit.ink(p.muted, bg), bg)] if it["right"] else []
    return V._row(kit, left + title, right, cols, bg)


def view(items: list, query: str, index: int, scroll: int, cols: int, rows: int, kit: U.Kit) -> PaletteView:
    """The list region for `rows` lines. With no query the groups get their headers; with one it is a flat ranked list. Never raises."""
    p = kit.p
    cols, rows = max(8, int(cols)), max(1, int(rows))
    shown = filter_items(items, query)
    index = max(0, min(int(index), max(0, len(shown) - 1)))
    flat: list = []                                      # ("header", text) | ("item", i)
    if (query or "").strip():
        flat = [("item", i) for i in range(len(shown))]
    else:
        last = None
        for i, it in enumerate(shown):
            if it["group"] != last:
                flat.append(("header", it["group"]))
                last = it["group"]
            flat.append(("item", i))
    pos = next((n for n, (kind, v) in enumerate(flat) if kind == "item" and v == index), 0)
    scroll = max(0, min(int(scroll), max(0, len(flat) - rows)))
    if pos < scroll:
        scroll = pos
    elif pos >= scroll + rows:
        scroll = pos - rows + 1
    if pos == scroll + 0 and scroll > 0 and flat[scroll - 1][0] == "header":
        scroll -= 1                                      # keep a group's header with its first picked row
    lines, hits = [], []
    for y, (kind, v) in enumerate(flat[scroll:scroll + rows]):
        if kind == "header":
            lines.append(kit.fit_line([U.S(f" {v}", kit.ink(p.faint, p.bar, 3.0), p.bar, bold=True)], cols, p.bar))
        else:
            lines.append(_row(kit, shown[v], v == index, cols))
            hits.append((y, v))
    while len(lines) < rows:
        lines.append(kit.blank(cols, p.bar))
    preview = []
    if shown:
        it = shown[index]
        words = it["title"].split()
        cur, wrapped = "", []
        for w in words:
            cand = (cur + " " + w).strip()
            if kit.cells(cand) <= cols - 4:
                cur = cand
            else:
                wrapped.append(cur)
                cur = w
        if cur:
            wrapped.append(cur)
        for line in wrapped[:PREVIEW_ROWS]:
            preview.append(kit.fit_line([U.S("  " + line, kit.ink(p.text, p.bar), p.bar)], cols, p.bar))
    elif (query or "").strip():
        preview = [kit.fit_line([U.S("  nothing matches “" + _text(query, 60) + "”", kit.ink(p.muted, p.bar), p.bar)], cols, p.bar)]
    return PaletteView(lines, hits, preview, scroll, len(shown))
