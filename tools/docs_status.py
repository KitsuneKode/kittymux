#!/usr/bin/env python3
"""Keep the feature-status tables in docs/users/what-you-can-do.mdx in step with docs/feature-status.yaml.

    python3 tools/docs_status.py            rewrite the block between the markers
    python3 tools/docs_status.py --check    exit 1 when the page is stale (what tests/test_docs.py and CI run)

The YAML is the editorial truth about product posture (shipped / beta / planned); the page shows it. Behaviour is still decided by code: this only
renders what the YAML says. Pure Python, no dependencies (the YAML here is a flat list of mappings of scalars)."""
import os
import re
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
YAML = os.path.join(ROOT, "docs", "feature-status.yaml")
PAGE = os.path.join(ROOT, "docs", "users", "what-you-can-do.mdx")
START, END = "{/* kittymux:status-table:start */}", "{/* kittymux:status-table:end */}"
ORDER = (("planned", "Planned", "Not built. The docs say so wherever they mention it."),
         ("beta", "Beta", "Works, with a stated gap."),
         ("shipped", "Shipped", "Works today and is covered by a test."))


def load_flat_yaml(text: str):
    """(top-level key, [mapping, …]) for the flat shapes docs/*.yaml use."""
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


def _cell(text: str) -> str:
    return text.replace("|", "\\|").strip()


def render(items) -> str:
    out = []
    for status, title, note in ORDER:
        rows = [i for i in items if i.get("status") == status]
        if not rows:
            continue
        out.append(f"### {title}\n\n{note}\n\n| Feature | What it does |\n| --- | --- |")
        out += [f"| {_cell(i['label'])} | {_cell(i['description'])} |" for i in rows]
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def sync(page_text: str, items) -> str:
    a, b = page_text.index(START), page_text.index(END)
    return page_text[:a + len(START)] + "\n\n" + render(items) + "\n" + page_text[b:]


def main(argv) -> int:
    with open(YAML, encoding="utf-8") as f:
        _key, items = load_flat_yaml(f.read())
    with open(PAGE, encoding="utf-8") as f:
        page = f.read()
    new = sync(page, items)
    if "--check" in argv:
        if new != page:
            print("docs/users/what-you-can-do.mdx is stale: run  python3 tools/docs_status.py", file=sys.stderr)
            return 1
        return 0
    if new != page:
        with open(PAGE, "w", encoding="utf-8") as f:
            f.write(new)
        print("updated docs/users/what-you-can-do.mdx")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
