#!/usr/bin/env python3
"""Facts for the documentation site, read from the repository itself so the site cannot drift from the product.
   python3 tools/export_facts.py > site/src/generated/facts.json"""
import importlib.util
import json
import os
import subprocess
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "python"))

import kittymux_agents  # noqa: E402
import kittymux_features  # noqa: E402
import kittymux_state  # noqa: E402

AGENT_NAMES = {"claude": "Claude Code", "codex": "Codex", "cursor-agent": "Cursor Agent", "gemini": "Gemini CLI", "opencode": "opencode",
               "amp": "Amp", "devin": "Devin", "agy": "Antigravity", "aider": "Aider", "crush": "Crush", "grok": "Grok", "droid": "Droid",
               "qwen": "Qwen Code", "kimi": "Kimi", "goose": "Goose", "kilo": "Kilo", "vibe": "Mistral Vibe", "junie": "Junie", "auggie": "Auggie"}
STATE_TEXT = {
    "limited": ("⊘", "A usage limit or quota is exhausted. Nothing happens until it resets, and the tab says when."),
    "waiting": ("!", "It is asking you something: a permission prompt or a question."),
    "working": ("⠋", "It is busy. The spinner turns."),
    "done": ("✓", "It finished while you were elsewhere. It clears when you look."),
    "idle": ("", "An agent is running and not doing anything."),
    "unread": ("•", "Output arrived in a tab that has no agent."),
}
FEATURE_TEXT = {
    "folder": "The project and branch line under each tab.",
    "hue": "A stable colour per project.",
    "collide": "Emphasise the project of tabs that show the same title.",
    "sheet": "A side sheet for a tab (planned).",
    "hover": "Open the sheet on hover (planned).",
    "panetitle": "The same line in each pane's title bar.",
    "motion": "The working spinner turns.",
    "titles": "A tab is called by its task, or its project when the title is only a product name or a reply.",
    "sudo": "A notification when sudo, doas, su or pkexec waits for your password in a pane you are not looking at.",
    "loginprompt": "The same for ssh and git asking for a passphrase, a password or to trust a host.",
    "pkgprompt": "The same for pacman, paru, yay, apt and dnf waiting for a yes or a no.",
}


def keys_from_sections(sections):
    out = [{"section": name, "rows": [{"key": k, "desc": d} for k, d in rows]} for name, rows in sections if rows]
    if not out:
        raise ValueError("export_facts: the key template produced no chords (did its format change?)")
    return out


def _load_mux_keys():
    spec = importlib.util.spec_from_file_location("mux_keys", os.path.join(ROOT, "bin", "mux-keys.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _version(root):
    try:
        out = subprocess.run(["git", "describe", "--tags", "--always", "--dirty"], cwd=root, capture_output=True, text=True, timeout=10)
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def build_facts(root=ROOT):
    mux = _load_mux_keys()
    keys = keys_from_sections(mux.parse_conf(os.path.join(root, "kittymux-keys.conf.tpl")))
    with open(os.path.join(root, "assets", "resume-agents.json"), encoding="utf-8") as f:
        resumable = {k for k in json.load(f) if not k.startswith("_")}
    seen, agents = set(), []
    for name, a in kittymux_agents.AGENTS.items():      # the table lists aliases (cursor/cursor-agent, agy/antigravity): one row per mark
        mark = (a.glyph, a.brand)
        if mark in seen:
            continue
        seen.add(mark)
        agents.append({"id": name, "name": AGENT_NAMES.get(name, name), "resumable": name in resumable})
    order = sorted((s for s in kittymux_state.PRIORITY if s), key=lambda s: -kittymux_state.PRIORITY[s])
    states = [{"id": s, "glyph": STATE_TEXT[s][0], "title": s, "meaning": STATE_TEXT[s][1]} for s in order + ["unread"]]
    live = kittymux_features.live()
    features = [{"id": f, "default": bool(kittymux_features.DEFAULTS[f]), "live": f in live, "summary": FEATURE_TEXT.get(f, "")}
                for f in kittymux_features.FEATURES]
    return {"version": _version(root), "keys": keys, "chords": sum(len(s["rows"]) for s in keys),
            "agents": agents, "states": states, "features": features}


if __name__ == "__main__":
    json.dump(build_facts(), sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
