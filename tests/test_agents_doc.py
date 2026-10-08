"""The agent guide stays lean, honest and complete: AGENTS.md is the short contract, docs/agents/ holds the detail, and neither names a script that does not exist
or leaves one out. (The guide was one 49 KB file; it is split so an agent reads what it needs, and this test keeps the split from rotting.)"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGES = ("layout", "status-contract", "conventions", "verify")
SCRIPT = re.compile(r"\b((?:smoke|shot|stress|soak|profile)_[a-z0-9_]+|test_(?:mux_status|socket_lib|panel_focus|install))\b")   # rigs and shell tests; unit tests are found by discovery


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def test_scripts():
    """Every shell rig/test in tests/ (probe_*.sh are one-off probes, described by one line)."""
    return {os.path.splitext(n)[0] for n in os.listdir(os.path.join(ROOT, "tests")) if n.endswith(".sh") and not n.startswith("probe_")}


class AgentGuide(unittest.TestCase):
    def test_the_contract_is_short_and_says_who_it_is_for(self):
        text = read("AGENTS.md")
        self.assertLess(len(text), 16_000, "AGENTS.md is the short contract: move detail into docs/agents/")
        for heading in ("## Who this file is for", "## What lives where", "## Read before you change, run after", "## How work flows", "## Definition of done", "## Rules"):
            self.assertIn(heading, text)

    def test_every_page_exists_and_is_linked(self):
        text = read("AGENTS.md")
        for page in PAGES:
            self.assertTrue(os.path.exists(os.path.join(ROOT, "docs", "agents", page + ".md")), page)
            self.assertIn(f"docs/agents/{page}.md", text, f"AGENTS.md does not point at {page}.md")

    def test_every_page_points_back(self):
        for page in PAGES:
            self.assertIn("AGENTS.md", read("docs", "agents", page + ".md"), page)

    def test_named_scripts_exist(self):
        have = test_scripts()
        for where in (("AGENTS.md",),) + tuple(("docs", "agents", p + ".md") for p in PAGES):
            for name in set(SCRIPT.findall(read(*where))):
                self.assertIn(name, have, f"{'/'.join(where)} names {name}, which is not in tests/")

    def test_no_script_is_left_out(self):
        text = read("AGENTS.md") + "".join(read("docs", "agents", p + ".md") for p in PAGES)
        named = set(SCRIPT.findall(text))
        for name in sorted(test_scripts()):
            self.assertIn(name, named, f"tests/{name} is described nowhere in the agent guide: add it to docs/agents/verify.md")

    def test_paths_in_the_tables_exist(self):
        for where in (("AGENTS.md",),) + tuple(("docs", "agents", p + ".md") for p in PAGES):
            for path in set(re.findall(r"`((?:docs|site|tests|tools|bin|python|lib|assets)/[A-Za-z0-9_./*-]+\.(?:md|mdx|py|sh|mjs|json|yml|yaml|tpl))`", read(*where))):
                if "*" in path or path.startswith("docs/superpowers"):
                    continue
                self.assertTrue(os.path.exists(os.path.join(ROOT, path)), f"{'/'.join(where)} names {path}, which does not exist")


if __name__ == "__main__":
    unittest.main()
