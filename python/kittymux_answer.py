"""`kittymux answer`: answer an agent's prompt from outside its pane (the rice notch's Allow / Deny), pure.

plan() is the whole decision: given what was asked, the agent's agents.json row and the pane's screen READ JUST NOW, it returns
the keys to type into that one pane, or None and why not. Nothing is typed unless the same prompt is still on screen; only the
agents whose prompts were captured live answer allow/deny (docs/compatibility.md); a typed answer is one plain line.
"""
from __future__ import annotations

import re

import kittymux_state

# allow / deny keys per agent, for the permission menus captured live (tests/test_state.py's screens)
KEYS = {
    "claude": {"allow": "1", "deny": "\x1b"},     # "❯ 1. Yes" / "3. No, and tell Claude what to do differently (esc)"
    "codex": {"allow": "\r", "deny": "\x1b"},     # "Press enter to confirm or esc to cancel"
}
TEXT_MAX = 2000
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def _norm(q) -> str:
    return " ".join(str(q or "").split())


def clean_text(text: str) -> str:
    """One plain line: newlines and tabs become spaces, control characters (ESC included) are dropped."""
    return _CTRL.sub("", re.sub(r"[\r\n\t]+", " ", str(text or "")))[:TEXT_MAX].strip()


def plan(how: str, row: dict, screen: str, expect=None, text: str = ""):
    """(keys, "") to send, or (None, why) when nothing may be typed."""
    agent = str((row or {}).get("agent") or "")
    marker, question = kittymux_state.classify_screen(screen or "")
    if expect is not None and how in ("allow", "deny") and marker == "waiting" and _norm(question) != _norm(expect):
        return None, f"the prompt changed: it now asks {question!r}"
    if how in ("allow", "deny"):
        if marker != "waiting":
            return None, "that prompt is no longer on screen"
        keys = KEYS.get(agent, {}).get(how)
        if keys is None:
            return None, f"{agent or 'this agent'}'s prompt is not verified for allow/deny; answer it in its pane"
        return keys, ""
    if how == "text":
        if marker == "waiting":
            return None, "a menu is on screen: answer it with allow or deny"
        if (row or {}).get("state") != "waiting" or not (row or {}).get("question"):
            return None, "it is not waiting for an answer"
        if expect is not None and _norm(row.get("question")) != _norm(expect):
            return None, f"the question changed: it now asks {row.get('question')!r}"
        line = clean_text(text)
        if not line:
            return None, "nothing to type"
        return line + "\r", ""
    return None, f"unknown answer {how!r} (allow, deny or text)"
