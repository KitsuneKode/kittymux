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
    "agy", "antigravity", "droid",
})

_TAIL_LINES = 14            # only the bottom of the screen: footers/prompts live there, stale output does not
_MARKER_GRACE = 1.5         # a positive marker keeps its state this long after it vanishes (repaint flicker)
_HOOK_GRACE = 4.0           # a hook said "working" but no marker has appeared yet (TUI still drawing)
_TITLE_FRESH = 6.0          # agents we cannot read: a title change this recent means "busy"
_HOOK_DONE_FRESH = 30.0     # a hook "done"/idle-"waiting" only means "just finished" while it is this recent; an old one is
                            # a leftover (window user vars outlive an agent) and would call a busy agent finished
_TURN_ABANDONED = 180.0     # a hook-announced turn with no Stop hook and no activity marker this long is dropped (Esc interrupts fire no Stop)
_HOOK_WAIT_FRESH = 300.0    # a hook-only "waiting" (no prompt on screen) is not held forever

_I = re.IGNORECASE
LIMITED_RE = re.compile(
    r"(?:usage|rate|weekly|daily|monthly|5-?hour|session)\s+limit\s+(?:reached|hit|exceeded)"
    r"|you(?:'|’)ve\s+(?:hit|reached)\s+(?:your|the)\s+[\w\s-]{0,20}limit"
    r"|quota\s+(?:exceeded|exhausted)|resource\s+has\s+been\s+exhausted"
    r"|credits?\s+(?:exhausted|depleted)|out\s+of\s+(?:acus?|credits)"
    r"|no\s+active\s+subscription",                         # Factory droid: "No active subscription found."
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
    # Devin swaps its input placeholder while it works ("Guide Devin while it works" vs "Ask Devin to build features…"):
    # present for the WHOLE turn, including moments when its "Thinking ·" line is not drawn
    r"|\bguide\s+devin\s+while\s+it\s+works\b"
    # Claude Code's spinner line, which newer versions print WITHOUT an "esc to interrupt" hint:
    # "· Undulating… (6m 52s · ↓ 35.8k tokens)"
    r"|[a-z][\w'’-]*(?:…|\.\.\.)\s*\(\s*(?:\d+\s*[hms]\s*)+(?:[·•]|\))"
    # a status line "Verb-ing … (12s •" with no ellipsis and no "esc" hint: Codex's "• Reviewing approval request (3s)"
    r"|^\W{0,3}[A-Z][a-z]+ing\b[^()\n]{0,50}\(\s*(?:\d+\s*[hms]\s*)+(?:[·•]|\))",
    _I)


# chrome only a real dialog draws: if one of these sits at or below a question, it IS the dialog even with a spinner nearby
_DIALOG_CHROME_RE = re.compile(
    r"\(esc\)|esc\s+to\s+cancel|enter\s+to\s+(?:confirm|select)|tab\s+to\s+amend|don(?:'|’)t\s+ask\s+again", _I)


def classify_screen(text: str) -> tuple[str, str]:
    """(marker, line) for the bottom of a pane's screen: marker is one of
    "limited" | "waiting" | "working" | "" (nothing recognisable); line is the matching
    line (stripped, bounded) so it can be shown as the reason.

    A question/limit match only counts when no activity hint is drawn BELOW it (unless dialog chrome such
    as "esc to cancel" is there too): a real prompt or limit notice is the last thing on screen (the agent
    stops animating), while the same words inside the agent's own reply scroll above a live spinner.
    Without this, an agent explaining "(y/n)" or "usage limit reached" while it works looked like a
    request for you."""
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()][-_TAIL_LINES:]
    working_at = next((i for i in range(len(lines) - 1, -1, -1) if WORKING_RE.search(lines[i])), -1)
    for marker, rx in (("limited", LIMITED_RE), ("waiting", WAITING_RE), ("working", WORKING_RE)):
        # a prompt's question sits above its options, so the first match is the reason to show;
        # for activity hints the nearest-the-bottom one is the live one
        for i in (range(len(lines)) if marker == "waiting" else range(len(lines) - 1, -1, -1)):
            if rx.search(lines[i]):
                if marker != "working" and working_at > i and not any(_DIALOG_CHROME_RE.search(x) for x in lines[i:]):
                    break                          # activity below it: that text is stale output, not a prompt
                return marker, lines[i][:160]
    return "", ""


# A hook "waiting" is a real request when its message reads like one. Claude also fires a
# Notification ~60 s after it finishes ("Claude is waiting for your input") — that is idleness, not a
# request, and must not turn a finished agent into a permanent "!".
_REQUEST_RE = re.compile(r"permission|approv|confirm|needs\s+your|\ballow\b|proceed|authori[sz]|\?\s*$", _I)


def is_request(msg: str) -> bool:
    return bool(msg and _REQUEST_RE.search(msg) and not re.search(r"waiting\s+for\s+your\s+input", msg, _I))


def _why(entry: dict, state: str, text: str) -> str:
    """Record WHY the resolver answered `state` (the private `why` key; `kittymux explain` shows it) and return it. Static strings only, so
    they never make the published verdict change when nothing else did."""
    entry["why"] = text
    return state


def resolve(entry: dict, agent: str | None, marker: str, now: float, focused: bool) -> str:
    """The pane's state: limited | waiting | working | done | idle | "" (no agent).

    `entry` is the watcher's bookkeeping dict for the window. This function keeps a few private
    keys in it (`marker`, `marker_ts`, `seen_working`, `unseen`, `ack_ts`, `why`, …) — its only mutation —
    so it can debounce and remember an unseen completion between calls."""
    if not agent:
        return ""
    explicit = entry.get("status") or ""
    ts_status = float(entry.get("ts_status") or 0)

    if agent not in SCREEN_AGENTS:
        # an agent whose TUI we cannot read: hooks if it has them, else recent title activity
        if explicit == "done":
            if focused:
                entry["ack_ts"] = ts_status
            seen = entry.get("ack_ts") == ts_status
            return _why(entry, "idle" if seen else "done", "its done hook fired" + (" and you have seen it" if seen else ", unseen"))
        if explicit in STATES:
            return _why(entry, explicit, f"its hook says {explicit} (this agent's screen is not read)")
        ts_title = float(entry.get("ts_title") or 0)
        busy = bool(ts_title and (now - ts_title) < _TITLE_FRESH)
        return _why(entry, "working" if busy else "idle", "its title changed a moment ago" if busy else "no hook and no title activity")

    if marker:
        entry["marker"], entry["marker_ts"] = marker, now
    else:
        held = entry.get("marker") or ""
        if held and now - float(entry.get("marker_ts") or 0) < _MARKER_GRACE:
            marker = held                          # a one-frame gap while the TUI repaints

    if marker in ("limited", "waiting"):
        entry["seen_working"], entry["unseen"] = False, False
        return _why(entry, marker, "the screen shows a usage-limit message" if marker == "limited"
                    else "the screen shows a permission/question prompt")
    if explicit == "working" and ts_status > float(entry.get("hook_turn_ts") or 0):
        entry["hook_turn"], entry["hook_turn_ts"] = True, ts_status    # a hook announced this turn: its Stop hook ends it
    if marker == "working":
        entry["seen_working"], entry["unseen"], entry["completed"] = True, False, False
        if explicit == "waiting":
            # Resumed work proves this particular permission request was handled.
            entry["handled_wait_ts"] = ts_status
        return _why(entry, "working", "the screen shows a busy marker")

    # nothing recognisable on screen
    if explicit == "working" and now - ts_status < _HOOK_GRACE:
        return _why(entry, "working", "its hook said working and the TUI has not drawn yet")
    if (explicit == "waiting" and entry.get("handled_wait_ts") != ts_status
            and is_request(entry.get("msg", "")) and now - ts_status < _HOOK_WAIT_FRESH):
        return _why(entry, "waiting", "its hook asked for you and nothing on screen contradicts it")
    if entry.get("hook_turn") and now - float(entry.get("marker_ts") or 0) > _TURN_ABANDONED:
        entry["hook_turn"] = False                 # no Stop hook and quiet for minutes: interrupted, not finished
    if entry.pop("seen_working", False):
        # it was busy and now is not. When a hook announced the turn (UserPromptSubmit), the agent itself says when it
        # ends (Stop hook) — a quiet screen between tool calls, a repaint or an interrupt is not a completion.
        # Agents without hooks are judged by the screen alone.
        if not entry.get("hook_turn"):
            entry["unseen"], entry["completed"] = True, True
            entry["unseen_cause"] = "the screen was busy and went quiet (no hook announced this turn)"
    stop_hook = explicit == "done"
    idle_hook = explicit == "waiting" and bool(ts_status) and not is_request(entry.get("msg", "")) and not entry.get("completed")
    if (stop_hook or idle_hook) and now - ts_status < _HOOK_DONE_FRESH:
        # a Stop hook, or an idle notification (not a request) when no completion was reported yet: the agent
        # finished and is waiting for its next prompt — an unseen completion until you look at it. Only while the
        # hook is fresh: an old one is a leftover and must not turn a repaint gap into "finished". A permission
        # request you already answered is NOT this: it is why the agent was waiting, not that it finished.
        if entry.get("ack_ts") != ts_status:
            entry["unseen"], entry["completed"] = True, True
            entry["unseen_cause"] = "its Stop hook fired" if stop_hook else "its idle notice arrived and no completion was reported yet"
        if stop_hook:
            entry["hook_turn"] = False
    if focused:
        entry["unseen"] = False                    # you are looking at it
        entry["ack_ts"] = ts_status
    if entry.get("unseen"):
        return _why(entry, "done", entry.get("unseen_cause") or "an unseen completion")
    if entry.get("hook_turn"):
        return _why(entry, "idle", "quiet, but a hook announced the turn: only its Stop hook can finish it")
    return _why(entry, "idle", "you are looking at it" if focused else "quiet: nothing on screen and no fresh hook")


def rollup(states) -> str:
    """The most important state among several panes/tabs (t3code's project roll-up)."""
    best = ""
    for s in states:
        if PRIORITY.get(s, 0) > PRIORITY.get(best, 0):
            best = s
    return best
