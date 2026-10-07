"""What a tab is CALLED (pure): the one place the bar and the panel decide how a program's window title is shown.

Agents set the window title to whatever they like: a real conversation title ("Port Hyprland configs to Lua"), the product name ("Claude Code"),
the user's first prompt, or - often - a sentence of their own reply ("I can't do that. I don't have access to the files"). The last kind says
nothing about the tab, and it is the one thing on the row that is read first. So:

  * a title is cleaned (control characters, markdown, quotes, trailing punctuation) and shortened at a WORD, with an ellipsis;
  * the agent's product name, or an assistant-sounding reply, is not a title: the tab is called by its PROJECT instead (the folder or repo it is in);
  * a title you gave a tab yourself, or a real task title, is never touched beyond cleaning.

Nothing is invented: the text shown is always the title itself (cleaned and shortened), or the project name, or the folder."""
from __future__ import annotations

import re
from typing import Callable, NamedTuple

import kittymux_agents
import kittymux_place

PLAIN, PROJECT, REPLY = "plain", "project", "reply"       # what `kind` says: the title as given, the project instead of a name, the project instead of a reply

_APOS = r"['’]?"
# openers that only an assistant answering someone says; a task title ("Add pane swapping"), a noun phrase or a question to the user is not here
_REPLY = re.compile(
    r"^(?:"
    r"i\s*(?:can" + _APOS + r"t|cannot|can\s+not|couldn" + _APOS + r"t|don" + _APOS + r"t|do\s+not|won" + _APOS + r"t|didn" + _APOS + r"t|"
    r"will|" + _APOS + r"ll|am|" + _APOS + r"m|have|" + _APOS + r"ve|would|need\s+to|think|see|found|noticed|apologi[sz]e|appreciate|understand)"
    r"|i\s+(?:can|could|should|might|did|was|got|ran|made|updated|added|fixed|checked|looked|tried)"
    r"|sorry|unfortunately|apologies|certainly|of\s+course|absolutely|understood|got\s+it|thanks\s+for|thank\s+you\s+for"
    r"|here" + _APOS + r"s|here\s+(?:is|are)|let\s+me|let" + _APOS + r"s|looks\s+like|it\s+looks|it\s+seems|that" + _APOS + r"s|there\s+(?:is|are|was|were)"
    r"|you" + _APOS + r"re|you\s+are|you\s+(?:can|could|should|might|need|have)|your\s+(?:request|question|code|file)|as\s+an\s+ai"
    r")\b"
    # interjections are also ordinary words ("Okay button styles", "Yes/no prompts", "Great Expectations"): they only open a reply when punctuation follows
    r"|^(?:sure|okay|ok|alright|great|perfect|thanks|thank\s+you|yes|no|done|right|good|nice)\s*[,.!:;\u2014]",
    re.I)
_MARKDOWN = re.compile(r"(\*\*|__|`+|^#+\s*|^>\s*|^[-*]\s+)")
_QUOTES = "\"'“”‘’"
_TRAIL = " .:;,…—-"
_SENTENCE_END = re.compile(r"(?<=[a-z0-9\)\]])[.!?]\s+(?=[A-Z“\"'])")


class Title(NamedTuple):
    text: str
    kind: str          # PLAIN | PROJECT | REPLY


def clean(raw) -> str:
    """One line of plain text: no control characters, no markdown, no wrapping quotes, no trailing punctuation."""
    text = kittymux_place.clean(str(raw if raw is not None else ""))[:400]
    text = kittymux_agents.strip_title_prefix(text)
    text = _MARKDOWN.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) >= 2 and text[0] in _QUOTES and text[-1] in _QUOTES:
        text = text[1:-1].strip()
    return text.rstrip(_TRAIL)


def looks_like_reply(text: str) -> bool:
    """Does this read as an assistant answering, not as a name? Conservative: a short noun-phrase or imperative is never a reply."""
    t = text.strip()
    if not t:
        return False
    if _REPLY.match(t):
        return True
    return len(t) > 60 and bool(_SENTENCE_END.search(t)) and t.count(" ") >= 9       # two sentences of prose is a message, not a name


def first_sentence(text: str) -> str:
    m = _SENTENCE_END.search(text)
    return text[:m.start() + 1].rstrip(_TRAIL) if m else text


_SUFFIX_SEP = re.compile(r"\s+[|\u2014\u2013\u00b7:\-]\s+")


def drop_project_suffix(text: str, project: str) -> str:
    """"Port the configs | hypr" in a tab whose project is "hypr" -> "Port the configs": some agents append the folder to their title, and the row's second
    line already says where the tab is. Only an EXACT, case-insensitive match of the project after a separator goes, and never the whole title."""
    if not project or not text:
        return text
    parts = _SUFFIX_SEP.split(text)
    if len(parts) < 2 or parts[-1].strip().lower() != project.strip().lower():
        return text
    seps = list(_SUFFIX_SEP.finditer(text))
    head = text[:seps[-1].start()].rstrip(_TRAIL)
    return head or text


def tidy(raw, agent: str | None = None, project: str = "", reply_to_project: bool = True) -> Title:
    """The title to show for a window title `raw` (already stripped of the agent's own name if the caller wants), in a tab whose project is `project`."""
    text = clean(raw)
    text = clean(kittymux_agents.strip_agent_prefix(text, agent)) if agent else text
    project = kittymux_place.clean(project or "").strip()
    if not text or (agent and kittymux_agents.is_default_title(text, agent)):
        return Title(project, PROJECT) if project else Title(text, PLAIN)
    if reply_to_project and project and looks_like_reply(text):
        return Title(project, REPLY)
    return Title(drop_project_suffix(text, project), PLAIN)


def shorten(text: str, width: int, cells: Callable[[str], int] = len) -> str:
    """`text` in at most `width` cells: cut at the last space when that keeps most of the room (a word is never left half-spelled), else at the
    cell; an ellipsis marks the cut."""
    if width <= 0:
        return ""
    if cells(text) <= width:
        return text
    if width == 1:
        return "…"
    room = width - 1
    cut, used = 0, 0
    for i, ch in enumerate(text):
        w = cells(ch)
        if used + w > room:
            break
        used += w
        cut = i + 1
    head = text[:cut]
    space = head.rfind(" ")
    if space >= max(3, int(len(head) * 0.6)):
        head = head[:space]
    return head.rstrip(_TRAIL + "/|·–") + "…"        # never a dangling separator in front of the ellipsis
