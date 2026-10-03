"""Guards for the published docs tree (docs/index.mdx, docs/users, docs/developer).

The tree is written to be dropped into a docs site as it is (TanStack Start + Fumadocs, as in kitsunesnipe): `title`/`description` frontmatter, `meta.json` navigation, `/docs/...` links,
standard Fumadocs components only. These tests are the drift guards that site will run too: a page nobody can reach, a link that goes nowhere, a shortcut that is not bound, a command the CLI
reference forgot. Code wins for behaviour; the docs explain it (docs/developer/docs-maintenance.mdx)."""
import json
import os
import re
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
DOCS = os.path.join(ROOT, "docs")
SECTIONS = ("users", "developer")
STATUSES = {"shipped", "beta", "planned"}

# how the docs spell a key that kitty's config spells another way (kitty accepts both PgUp and page_up)
KEY_ALIASES = {"pgup": "page_up", "pgdn": "page_down"}

# chords that the docs name on purpose although kittymux does NOT bind them: they are the user's own (docs/users/your-own-shortcuts.mdx)
NOT_OURS = {"ctrl+alt+shift+h", "ctrl+alt+shift+k", "ctrl+alt+shift+v", "ctrl+alt+shift+z", "ctrl+alt+shift+f", "ctrl+alt+shift+x"}
# chords Hyprland (not kitty) owns, named where the docs explain why kittymux avoids them
WM_OWNED = {"ctrl+alt+a", "ctrl+alt+s", "ctrl+alt+f", "ctrl+alt+c", "ctrl+alt+x", "ctrl+alt+p", "ctrl+alt+w", "ctrl+alt+m",
            "ctrl+alt+left", "ctrl+alt+right"}      # the arrows pass through to tmux only while it has focus (--when-focus-on), and WMs take them otherwise


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def page_paths():
    out = [os.path.join(DOCS, "index.mdx")]
    for section in SECTIONS:
        d = os.path.join(DOCS, section)
        if os.path.isdir(d):
            out += [os.path.join(d, n) for n in sorted(os.listdir(d)) if n.endswith(".mdx")]
    return [p for p in out if os.path.exists(p)]


def route(path):
    rel = os.path.relpath(path, DOCS)[:-4]
    if rel == "index":
        return "/docs"
    return "/docs/" + (rel[:-6] if rel.endswith("/index") else rel).rstrip("/")


def frontmatter(text):
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    out = {}
    if m:
        for line in m.group(1).splitlines():
            k, _, v = line.partition(":")
            out[k.strip()] = v.strip().strip('"')
    return out


def body(text):
    return re.sub(r"\A---\n.*?\n---\n", "", text, count=1, flags=re.S)


def slug(heading):
    s = re.sub(r"`", "", heading.strip().lower())
    s = re.sub(r"[^\w\s-]", "", s)
    return re.sub(r"\s", "-", s)


def headings(text):
    out = []
    fenced = False
    for line in body(text).splitlines():
        if line.startswith("```"):
            fenced = not fenced
        elif not fenced:
            m = re.match(r"#{1,6}\s+(.*?)\s*$", line)
            if m:
                out.append(m.group(1))
    return out


def load_flat_yaml(text):
    """The flat shapes docs/*.yaml use: one top-level key holding a list of mappings of scalars. No dependency on PyYAML."""
    items, key = [], None
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.match(r"^(\w+):\s*$", line)
        if m:
            key = m.group(1)
            continue
        m = re.match(r"^  - (\w+):\s*(.*)$", line)
        if m:
            items.append({m.group(1): m.group(2).strip().strip('"')})
            continue
        m = re.match(r"^    (\w+):\s*(.*)$", line)
        if m and items:
            items[-1][m.group(1)] = m.group(2).strip().strip('"')
    return key, items


class PageTests(unittest.TestCase):
    def test_the_tree_exists(self):
        self.assertTrue(os.path.exists(os.path.join(DOCS, "index.mdx")))
        for s in SECTIONS:
            self.assertTrue(os.path.exists(os.path.join(DOCS, s, "index.mdx")), f"docs/{s}/index.mdx")
        self.assertGreaterEqual(len(page_paths()), 20)

    def test_every_page_has_a_title_and_a_description(self):
        for p in page_paths():
            fm = frontmatter(read(p))
            self.assertTrue(fm.get("title"), f"{p}: title")
            d = fm.get("description", "")
            self.assertTrue(60 <= len(d) <= 220, f"{p}: description is {len(d)} characters (aim for 60-220)")

    def test_titles_and_descriptions_are_unique(self):
        for field in ("title", "description"):
            seen = {}
            for p in page_paths():
                v = frontmatter(read(p)).get(field)
                self.assertNotIn(v, seen, f"{field} of {p} repeats {seen.get(v)}")
                seen[v] = p

    def test_no_page_is_unfinished(self):
        for p in page_paths():
            self.assertNotRegex(read(p), r"(?i)\b(TODO|TBD|FIXME|lorem ipsum)\b", p)


class NavigationTests(unittest.TestCase):
    def test_root_navigation_lists_the_sections(self):
        meta = json.loads(read(os.path.join(DOCS, "meta.json")))
        self.assertEqual(meta["pages"], ["index", "users", "developer"])

    def test_every_section_lists_exactly_its_pages(self):
        for s in SECTIONS:
            meta = json.loads(read(os.path.join(DOCS, s, "meta.json")))
            for k in ("title", "description", "icon", "pages"):
                self.assertIn(k, meta, f"docs/{s}/meta.json: {k}")
            self.assertTrue(meta.get("root"), f"docs/{s}/meta.json is a root section")
            listed = meta["pages"]
            self.assertEqual(len(listed), len(set(listed)), f"docs/{s}/meta.json lists a page twice")
            self.assertEqual(listed[0], "index")
            files = sorted(n[:-4] for n in os.listdir(os.path.join(DOCS, s)) if n.endswith(".mdx"))
            self.assertEqual(sorted(listed), files, f"docs/{s}: pages on disk and in meta.json differ")


class LinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.routes = {route(p): p for p in page_paths()}
        cls.anchors = {r: {slug(h) for h in headings(read(p))} for r, p in cls.routes.items()}

    def links(self, path):
        text = body(read(path))
        text = re.sub(r"```.*?```", "", text, flags=re.S)
        text = re.sub(r"`[^`\n]*`", "", text)
        return re.findall(r"(?<!!)\[([^\]]*)\]\(([^)\s]+)\)", text)

    def test_every_docs_link_resolves_to_a_page_and_a_heading(self):
        for p in page_paths():
            for label, target in self.links(p):
                if not target.startswith("/docs"):
                    continue
                page, _, anchor = target.partition("#")
                self.assertIn(page.rstrip("/") or "/docs", self.routes, f"{p}: [{label}]({target}) goes nowhere")
                if anchor:
                    self.assertIn(anchor, self.anchors[page.rstrip("/")], f"{p}: [{label}]({target}) — no such heading")

    def test_same_page_anchors_resolve(self):
        for p in page_paths():
            mine = {slug(h) for h in headings(read(p))}
            for label, target in self.links(p):
                if target.startswith("#"):
                    self.assertIn(target[1:], mine, f"{p}: [{label}]({target})")

    def test_only_links_a_docs_site_can_follow(self):
        """Repository-relative links (../README.md) work on GitHub and 404 on a site: link to a /docs page, an https URL or an anchor."""
        for p in page_paths():
            for label, target in self.links(p):
                self.assertRegex(target, r"^(/docs|https://|mailto:|#)", f"{p}: [{label}]({target})")

    def test_link_text_says_where_the_link_goes(self):
        for p in page_paths():
            for label, target in self.links(p):
                self.assertNotRegex(label.strip().lower(), r"^(here|click here|this|link|learn more|read more|more)$", f"{p}: [{label}]({target})")


class ImageTests(unittest.TestCase):
    def test_images_are_served_from_assets_and_exist(self):
        """A docs site serves the repository's assets/ folder at /assets/ (docs/developer/docs-maintenance.mdx)."""
        for p in page_paths():
            text = re.sub(r"`[^`\n]*`", "", re.sub(r"```.*?```", "", body(read(p)), flags=re.S))
            for alt, target in re.findall(r"!\[([^\]]*)\]\(([^)\s]+)\)", text):
                self.assertTrue(alt.strip(), f"{p}: image {target} has no alt text")
                self.assertTrue(target.startswith("/assets/"), f"{p}: image {target}")
                self.assertTrue(os.path.exists(os.path.join(ROOT, target[1:])), f"{p}: {target} is not in the repository's assets/")


class MdxSafetyTests(unittest.TestCase):
    """What MDX would choke on at build time, caught here because the site is not built yet."""
    COMPONENTS = {"Callout", "Steps", "Step", "Cards", "Card", "Tabs", "Tab"}

    @staticmethod
    def prose(text):
        text = re.sub(r"```.*?```", "", body(text), flags=re.S)
        text = re.sub(r"``[^\n]+?``", "", text)
        text = re.sub(r"`[^`\n]*`", "", text)
        return re.sub(r"\{/\*.*?\*/\}", "", text, flags=re.S)

    def test_no_stray_braces_or_tags_in_prose(self):
        for p in page_paths():
            for n, line in enumerate(self.prose(read(p)).splitlines(), 1):
                self.assertNotRegex(line, r"[{}]", f"{p}: a brace outside code ({line.strip()[:60]})")
                for tag in re.findall(r"</?([A-Za-z][\w-]*)", line):
                    self.assertIn(tag, self.COMPONENTS, f"{p}: <{tag}> outside code is not a known component")
                self.assertNotRegex(line, r"<[^A-Za-z/!]", f"{p}: a bare < outside code")

    def test_tags_are_balanced(self):
        for p in page_paths():
            text = self.prose(read(p))
            for tag in ("Callout", "Steps", "Step", "Cards", "Card"):
                self.assertEqual(len(re.findall(rf"<{tag}[\s>]", text)), len(re.findall(rf"</{tag}>", text)), f"{p}: <{tag}> is not closed")

    def test_markdown_inside_a_step_is_separated_by_blank_lines(self):
        """Fumadocs documents <Step> with blank lines around the heading and the body; without them MDX reads the heading as text."""
        for p in page_paths():
            text = read(p)
            self.assertNotRegex(text, r"<Step>\n(?!\n)", f"{p}: no blank line after <Step>")
            self.assertNotRegex(text, r"(?m)^### .*\n(?!\n)(?=[^<])", f"{p}: no blank line after a heading") if "<Step>" in text else None

    def test_callouts_use_known_types(self):
        for p in page_paths():
            for t in re.findall(r'<Callout[^>]*\btype="(\w+)"', read(p)):
                self.assertIn(t, {"info", "warn", "warning", "error", "success", "idea"}, p)

    def test_generated_text_is_mdx_safe(self):
        _k, items = load_flat_yaml(read(os.path.join(DOCS, "feature-status.yaml")))
        for i in items:
            for field in ("label", "description"):
                self.assertNotRegex(i[field], r"[{}<>|]", f"feature-status.yaml {i['id']}.{field}")


class ShortcutTests(unittest.TestCase):
    """A chord the docs name must be one kittymux really binds — the same guard the README key table has."""

    @classmethod
    def setUpClass(cls):
        try:
            import test_readme_keys as R
        except ImportError:                                  # run as `python -m unittest tests.test_docs`
            from tests import test_readme_keys as R
        cls.R = R
        cls.bound = {R._norm(c) for c in R.tpl_chords() if not c.startswith("--")}      # modifier order does not matter: ctrl+shift+alt+r is ctrl+alt+shift+r

    def chords(self, text):
        text = re.sub(r"```.*?```", "", text, flags=re.S)
        spans = [m.strip() for m in re.findall(r"``\s*([^\n]+?)\s*``", text)]            # `` ctrl+alt+` `` — a code span that holds a backtick
        text = re.sub(r"``[^\n]+?``", "", text)
        for cell in spans + re.findall(r"`([^`\n]+)`", text):
            if re.match(r"^ctrl\+alt\+", cell) and self.R._CHORD.match(cell) and " " not in cell and ".." not in cell \
                    and "/" not in cell[:-1] and not cell.endswith("+arrows"):
                *mods, key = cell.split("+") if not cell.endswith("++") else (cell[:-2].split("+") + ["plus"])
                key = KEY_ALIASES.get(key.lower(), key)
                yield cell, "+".join(mods + [self.R._NAMES.get(key, key)]).lower()

    def test_every_ctrl_alt_chord_the_docs_name_is_bound(self):
        for p in page_paths():
            for shown, want in self.chords(read(p)):
                if want in NOT_OURS or want in WM_OWNED:
                    continue
                self.assertIn(self.R._norm(want), self.bound, f"{p}: `{shown}` is not bound by kittymux-keys.conf.tpl (renamed? removed?)")

    def test_the_shortcut_pages_exist_and_name_many_chords(self):
        text = read(os.path.join(DOCS, "users", "shortcuts.mdx"))
        self.assertGreater(len(list(self.chords(text))), 25)

    def test_chords_the_user_owns_are_never_listed_as_ours(self):
        """Naming them is fine on the page that explains them; a shortcuts table must not claim one."""
        text = read(os.path.join(DOCS, "users", "shortcuts.mdx"))
        named = {want for _shown, want in self.chords(text)}
        self.assertEqual(named & NOT_OURS, set(), "docs/users/shortcuts.mdx lists a chord kittymux leaves to you")


class CliReferenceTests(unittest.TestCase):
    def test_every_command_in_the_help_has_a_reference_entry(self):
        src = read(os.path.join(ROOT, "bin", "kittymux"))
        doc = src.split('"""', 2)[1]
        commands = re.findall(r"(?m)^  kittymux (\w+)\s", doc)
        self.assertGreater(len(commands), 15)
        ref = read(os.path.join(DOCS, "users", "cli-reference.mdx"))
        for c in commands:
            if c == "version":
                continue
            self.assertRegex(ref, rf"(?m)^#{{2,4}} `kittymux {c}\b", f"cli-reference.mdx has no entry for `kittymux {c}`")


class YamlTests(unittest.TestCase):
    def test_feature_status_uses_the_allowed_statuses(self):
        key, items = load_flat_yaml(read(os.path.join(DOCS, "feature-status.yaml")))
        self.assertEqual(key, "features")
        self.assertGreater(len(items), 20)
        ids = [i["id"] for i in items]
        self.assertEqual(len(ids), len(set(ids)))
        for i in items:
            self.assertIn(i.get("status"), STATUSES, i)
            self.assertTrue(i.get("label") and i.get("description"), i)

    def test_planned_features_say_so_in_the_docs_that_mention_them(self):
        _k, items = load_flat_yaml(read(os.path.join(DOCS, "feature-status.yaml")))
        planned = {i["id"] for i in items if i["status"] == "planned"}
        self.assertIn("side-sheet", planned)
        self.assertIn("hover-sheet", planned)

    def test_promotion_manifest_points_at_real_files(self):
        key, items = load_flat_yaml(read(os.path.join(DOCS, "promotion-manifest.yaml")))
        self.assertEqual(key, "promotions")
        self.assertGreater(len(items), 5)
        for i in items:
            self.assertTrue(os.path.exists(os.path.join(ROOT, i["agentPath"])), i["agentPath"])
            self.assertTrue(os.path.exists(os.path.join(ROOT, i["publishedPath"])), i["publishedPath"])
            self.assertRegex(i["lastReviewed"], r"^\d{4}-\d{2}-\d{2}$")

    def test_troubleshooting_symptoms_match_headings_on_the_page(self):
        key, items = load_flat_yaml(read(os.path.join(DOCS, "troubleshooting-symptoms.yaml")))
        self.assertEqual(key, "symptoms")
        heads = {h.lower() for h in headings(read(os.path.join(DOCS, "users", "troubleshooting.mdx")))}
        ids = [i["id"] for i in items]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreater(len(items), 6)
        for i in items:
            self.assertIn(i["anchor"].lower(), heads, f"troubleshooting.mdx has no heading '{i['anchor']}'")
            self.assertTrue(i["question"].endswith("?"), i)


def repo_source_text() -> str:
    """Everything a doc can truthfully point at: the code, the config and the templates (not docs, not tests)."""
    chunks = []
    for sub_dir in ("bin", "python", "lib", "assets", "tools"):
        for dirpath, _dirs, files in os.walk(os.path.join(ROOT, sub_dir)):
            if "__pycache__" in dirpath:
                continue
            for name in files:
                if name.endswith((".png", ".svg", ".ttf", ".otf", ".gif", ".pyc")):
                    continue
                try:
                    chunks.append(read(os.path.join(dirpath, name)))
                except (UnicodeDecodeError, OSError):
                    pass
    for name in ("kittymux.conf", "kittymux-keys.conf.tpl", "kittymux-leader.conf.tpl", "install.sh", "open-actions.conf.tpl"):
        chunks.append(read(os.path.join(ROOT, name)))
    return "\n".join(chunks)


class FactTests(unittest.TestCase):
    """The docs against the code, mechanically: a variable, command, flag file or path a page names must exist. They catch a typo today and a removed feature next year."""

    @classmethod
    def setUpClass(cls):
        cls.src = repo_source_text()
        cls.pages = {p: read(p) for p in page_paths()}

    @staticmethod
    def code_spans(text):
        text = re.sub(r"```.*?```", lambda m: m.group(0), text, flags=re.S)
        return re.findall(r"`([^`\n]+)`", text)

    def test_every_environment_variable_named_exists_in_the_code(self):
        sys.path.insert(0, os.path.join(ROOT, "python"))
        import kittymux_features
        dynamic = {f"KITTYMUX_{n.upper()}" for n in kittymux_features.FEATURES}          # read as f"KITTYMUX_{name.upper()}", so never a literal in the code
        for p, text in self.pages.items():
            for var in set(re.findall(r"\bKITTYMUX_[A-Z0-9_]+\b", text)):
                if var.endswith("_") or var in dynamic:
                    continue                                                                # `KITTYMUX_` alone is a prefix
                self.assertIn(var, self.src, f"{p}: {var} is not read anywhere in the code")

    def test_every_kittymux_command_in_code_exists(self):
        cli = read(os.path.join(ROOT, "bin", "kittymux"))
        known = set(re.findall(r'(?m)^    if cmd == "([\w-]+)"', cli))
        for group in re.findall(r"cmd in \(([^)]*)\)", cli):
            known |= set(re.findall(r'"([\w-]+)"', group))
        self.assertGreater(len(known), 15)
        for p, text in self.pages.items():
            code = "\n".join(re.findall(r"```[\w]*\n(.*?)```", text, flags=re.S)) + "\n" + "\n".join(self.code_spans(re.sub(r"```.*?```", "", text, flags=re.S)))
            code = "\n".join(re.sub(r"(^|\s)#.*$", "", line) for line in code.splitlines())              # shell comments are prose
            for cmd in set(re.findall(r"\bkittymux ([a-z][a-z-]+)\b", code)):
                self.assertIn(cmd, known, f"{p}: `kittymux {cmd}` is not a command")

    def test_every_repository_path_named_exists(self):
        for p, text in self.pages.items():
            for span in self.code_spans(text):
                m = re.match(r"^((?:python|bin|assets|tools|tests|lib|docs)/[\w./-]+?)(?::\d+)?$", span.strip())
                if not m or any(c in span for c in "<>*{}$ "):
                    continue
                path = m.group(1)
                self.assertTrue(os.path.exists(os.path.join(ROOT, path)), f"{p}: `{span}` is not in the repository")

    def test_every_flag_file_named_is_a_switch_in_the_code(self):
        for p, text in self.pages.items():
            for span in self.code_spans(text):
                for name in re.findall(r"(?<![\w/.-])([a-z]+(?:-[a-z]+)*-(?:off|on)|notify-private|attention-on|resume-auto)(?![\w-])", span):
                    self.assertIn(name, self.src, f"{p}: the flag file `{name}` is not read anywhere in the code")

    def test_every_key_the_picker_names_is_handled_by_its_kitten(self):
        """tabs-and-panes documents the join list's keys; each must appear in join-kit.py's key handler."""
        kit = read(os.path.join(ROOT, "python", "join-kit.py"))
        for token in ('"ESCAPE"', '"ENTER"', '"DOWN"', '"UP"', '"TAB"', '"BACKSPACE"', '"PAGE_DOWN"', '"PAGE_UP"'):
            self.assertIn(token, kit)
        self.assertIn('ctrl and k == "T"', kit)                  # ctrl+t
        self.assertIn('ctrl and k == "N"', kit)                  # ctrl+n
        self.assertIn('ctrl and k == "P"', kit)                  # ctrl+p
        self.assertIn('ctrl and k == "C"', kit)                  # ctrl+c


class StatusTableTests(unittest.TestCase):
    def test_the_generated_status_tables_are_fresh(self):
        """docs/users/what-you-can-do.mdx shows docs/feature-status.yaml; `python3 tools/docs_status.py` rewrites it."""
        import sys
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import docs_status
        _k, items = docs_status.load_flat_yaml(read(os.path.join(DOCS, "feature-status.yaml")))
        page = read(os.path.join(DOCS, "users", "what-you-can-do.mdx"))
        self.assertEqual(docs_status.sync(page, items), page, "what-you-can-do.mdx is stale: run python3 tools/docs_status.py")
        for i in items:
            self.assertIn(f"| {i['label']} |", page)

    def test_the_presets_the_docs_name_exist(self):
        sys.path.insert(0, os.path.join(ROOT, "python"))
        import kittymux_layout
        text = "".join(read(p) for p in page_paths())
        m = re.search(r"sidebar, rail, ([a-z-]+), bottom, top, zen", text)
        self.assertTrue(m)
        for name in ("sidebar", "rail", m.group(1), "bottom", "top", "zen"):
            self.assertIn(name, kittymux_layout.PRESETS)


class VoiceTests(unittest.TestCase):
    """The writing rules in code (better-writing): plain words, no blame, no shouting."""

    def test_headings_are_sentence_case_and_calm(self):
        for p in page_paths():
            for h in headings(read(p)):
                self.assertNotIn("!", h, f"{p}: heading '{h}'")
                self.assertNotRegex(h, r"(?i)\boops\b", f"{p}: heading '{h}'")
                words = re.findall(r"[A-Za-z][A-Za-z'’-]*", re.sub(r"`[^`]*`", "", h))
                caps = [w for w in words[1:] if w[0].isupper() and not w.isupper() and w not in KNOWN_PROPER]
                self.assertLessEqual(len(caps), 1, f"{p}: heading '{h}' is not sentence case ({caps})")

    def test_no_page_blames_the_reader(self):
        for p in page_paths():
            self.assertNotRegex(body(read(p)), r"(?i)\byou (forgot|failed|should have|must have)\b", p)
            self.assertNotRegex(body(read(p)), r"(?i)\boops\b", p)


# product and tool names that keep their capitals inside a sentence-case heading
KNOWN_PROPER = {"Claude", "Codex", "Devin", "Gemini", "Cursor", "OpenCode", "Amp", "Antigravity", "Hyprland", "Wayland", "Quickshell", "Fumadocs",
                "TanStack", "Start", "Kitty", "Home", "Linux", "Arch", "GitHub", "X11", "Xvfb", "Next", "Code", "CLI", "Git", "Rofi", "Waybar", "Fuzzel"}


if __name__ == "__main__":
    unittest.main()
