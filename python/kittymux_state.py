# kittymux state — what is an agent in this pane doing RIGHT NOW?
#
# Pure Python (no kitty imports; unit-tested). The watcher (pane-state.py) feeds it the pane's
# visible text and bookkeeping and stores the answer; every consumer (tab bar, deck, panel,
# `mux-agents.sh`) reads that one answer, so they can never disagree.
#
# Rules, borrowed from how t3code's sidebar resolves a thread (Sidebar.logic.ts):
#   * one ordered resolver — attention states outrank work, work outranks "completed";
#   * a state needs POSITIVE evidence. Silence is not "waiting": an agent that stopped
#     printing is usually just thinking, or finished;
#   * "done" means *unseen* completion — focusing the pane clears it;
#   * exhaustion (usage limit / quota) is its own state, not a flavour of "waiting".
#
# Order of importance (also used to roll several panes up into one tab/session):
#   limited > waiting > working > done > idle

import re

STATES = ("limited", "waiting", "working", "done", "idle")
PRIORITY = {"limited": 5, "waiting": 4, "working": 3, "done": 2, "idle": 1, "": 0}

# Agents whose TUIs draw "esc to interrupt"-style hints and permission prompts — for these
# the visible screen is the primary source of truth. Others (aider, crush, grok, unknown)
# only have hooks / title activity to go on.
SCREEN_AGENTS = frozenset({
    "claude", "codex", "cursor-agent", "cursor", "gemini", "opencode", "amp", "devin",
    "agy", "antigravity",
})

_TAIL_LINES = 14            # only the bottom of the screen: footers/prompts live there, stale output does not
_MARKER_GRACE = 1.5         # a positive marker keeps its state this long after it vanishes (repaint flicker)
_HOOK_GRACE = 4.0           # a hook said "working" but no marker has appeared yet (TUI still drawing)
_TITLE_FRESH = 6.0          # agents we cannot read: a title change this recent means "busy"

_I = re.IGNORECASE
LIMITED_RE = re.compile(
    r"(?:usage|rate|weekly|daily|monthly|5-?hour|session)\s+limit\s+(?:reached|hit|exceeded)"
    r"|you(?:'|’)ve\s+(?:hit|reached)\s+(?:your|the)\s+[\w\s-]{0,20}limit"
    r"|quota\s+(?:exceeded|exhausted)|resource\s+has\s+been\s+exhausted"
    r"|credits?\s+(?:exhausted|depleted)|out\s+of\s+(?:acus?|credits)",
    _I)
WAITING_RE = re.compile(
    r"do\s+you\s+want\s+to\s+(?:proceed|make\s+this\s+edit|create|allow|run|apply|overwrite)"
    r"|would\s+you\s+like\s+to\s+(?:run|apply|proceed|allow)"
    r"|\(y/n\)|\[y/n\]|\(yes/no\)"
    r"|[❯›>]\s*1\.\s+yes"
    r"|esc\s+to\s+cancel\s*[·•|]\s*tab\s+to\s+amend"
    r"|enter\s+to\s+select\s*[·•|]"
    r"|press\s+enter\s+to\s+confirm"
    r"|(?:allow|approve)\s+(?:this|once|always)"
    r"|yes,\s+(?:and\s+)?(?:allow|don(?:'|’)t\s+ask)"
    r"|waiting\s+for\s+(?:your\s+)?(?:approval|permission|confirmation)",
    _I)
WORKING_RE = re.compile(
    r"\besc(?:ape)?(?:\s+twice)?\s+to\s+(?:interrupt|cancel|stop)\b"
    r"|\bctrl\+c\s+to\s+(?:interrupt|stop|cancel)\b"
    r"|\besc\s+interrupt\b"
    # Claude Code's spinner line, which newer versions print WITHOUT an "esc to interrupt" hint:
    # "· Undulating… (6m 52s · ↓ 35.8k tokens)"
    r"|[a-z][\w'’-]*(?:…|\.\.\.)\s*\(\s*(?:\d+\s*[hms]\s*)+(?:[·•]|\))",
    _I)


def classify_screen(text: str) -> tuple[str, str]:
    """(marker, line) for the bottom of a pane's screen: marker is one of
    "limited" | "waiting" | "working" | "" (nothing recognisable); line is the matching
    line (stripped, bounded) so it can be shown as the reason."""
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()][-_TAIL_LINES:]
    for marker, rx in (("limited", LIMITED_RE), ("waiting", WAITING_RE), ("working", WORKING_RE)):
        # a prompt's question sits above its options, so the first match is the reason to show;
        # for activity hints the nearest-the-bottom one is the live one
        for ln in (lines if marker == "waiting" else reversed(lines)):
            if rx.search(ln):
                return marker, ln[:160]
    return "", ""


# A hook "waiting" is a real request when its message reads like one. Claude also fires a
# Notification ~60 s after it finishes ("Claude is waiting for your input") — that is idleness, not a
# request, and must not turn a finished agent into a permanent "!".
_REQUEST_RE = re.compile(r"permission|approv|confirm|needs\s+your|\ballow\b|proceed|authori[sz]|\?\s*$", _I)


def is_request(msg: str) -> bool:
    return bool(msg and _REQUEST_RE.search(msg) and not re.search(r"waiting\s+for\s+your\s+input", msg, _I))


def resolve(entry: dict, agent: str | None, marker: str, now: float, focused: bool) -> str:
    """The pane's state: limited | waiting | working | done | idle | "" (no agent).

    `entry` is the watcher's bookkeeping dict for the window. This function keeps a few private
    keys in it (`marker`, `marker_ts`, `seen_working`, `unseen`, `ack_ts`) — its only mutation —
    so it can debounce and remember an unseen completion between calls."""
    if not agent:
        return ""
    explicit = entry.get("status") or ""
    ts_status = float(entry.get("ts_status") or 0)

    if agent not in SCREEN_AGENTS:
        # an agent whose TUI we cannot read: hooks if it has them, else recent title activity
        if explicit in STATES:
            return explicit
        ts_title = float(entry.get("ts_title") or 0)
        return "working" if ts_title and (now - ts_title) < _TITLE_FRESH else "idle"

    if marker:
        entry["marker"], entry["marker_ts"] = marker, now
    else:
        held = entry.get("marker") or ""
        if held and now - float(entry.get("marker_ts") or 0) < _MARKER_GRACE:
            marker = held                          # a one-frame gap while the TUI repaints

    if marker in ("limited", "waiting"):
        entry["seen_working"], entry["unseen"] = False, False
        return marker
    if marker == "working":
        entry["seen_working"], entry["unseen"] = True, False
        return "working"

    # nothing recognisable on screen
    if explicit == "working" and now - ts_status < _HOOK_GRACE:
        return "working"                           # the hook just fired; the TUI has not drawn yet
    if explicit == "waiting" and is_request(entry.get("msg", "")):
        return "waiting"                           # a hook asked for you and nothing contradicts it
    if entry.pop("seen_working", False):
        entry["unseen"] = True                     # it was busy and now is not: a completion
    if explicit == "done" or (explicit == "waiting" and ts_status):
        # a Stop hook, or an idle notification after it (not a request): the agent finished and is
        # waiting for its next prompt — an unseen completion until you look at it
        if entry.get("ack_ts") != ts_status:
            entry["unseen"] = True
    if focused:
        entry["unseen"] = False                    # you are looking at it
        entry["ack_ts"] = ts_status
    return "done" if entry.get("unseen") else "idle"


def rollup(states) -> str:
    """The most important state among several panes/tabs (t3code's project roll-up)."""
    best = ""
    for s in states:
        if PRIORITY.get(s, 0) > PRIORITY.get(best, 0):
            best = s
    return best
