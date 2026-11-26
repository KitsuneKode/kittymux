"""What the vertical bar writes on a tab, as pure decisions (no kitty imports).

`display_title` and `show_program` were in the bar's own tabs.json publisher; tabs.json is now the
scanner's alone (kittymux_tabsnap, docs/inbox.md), and these stay here for the bar that draws.
"""
from __future__ import annotations


_PROJECT_SEPS = (":", " - ", " — ", " · ")


def strip_project_suffix(title: str, project: str) -> str:
    """`nvim:kitsunesnipe` under the group kitsunesnipe reads `nvim`: the separator is found in the title as it is and the rest
    compared case-insensitively, never sliced by a lowercased length ("İ".lower() is two code points). Unchanged otherwise."""
    if not title or not project:
        return title
    for sep in _PROJECT_SEPS:
        i = title.rfind(sep)
        if i > 0 and title[i + len(sep):].casefold() == project.casefold():
            head = title[:i].strip()
            if head:
                return head
    return title


def display_title(title: str) -> str:
    """The title the bar draws for a tidied string. A bare `~` (the home folder) is Home."""
    return "Home" if (title or "").strip() == "~" else (title or "")


def show_program(has_agent: bool, has_place: bool, home_only: bool, place_is_folder: bool) -> bool:
    """True when the bar draws the program instead of the folder line.

    No agent, and either there is no place line, or the line is only the home folder (it would
    repeat `~`). An agent keeps its place line. A legacy branch/path line is not the home folder.
    """
    if has_agent:
        return False
    if not has_place:
        return True
    return bool(home_only and place_is_folder)
