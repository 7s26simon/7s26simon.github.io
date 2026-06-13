#!/usr/bin/env python3
"""
convert-to-nav-include.py - Replace every inline <nav class="topnav">...</nav>
with a stub that loads the canonical nav from _includes/nav.html via JS.

Idempotent: re-running on already-converted files is a no-op.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Every HTML page in the project
TARGET_DIRS = [
    ROOT,
    ROOT / "htb-writeups",
    ROOT / "thm-writeups",
    ROOT / "vulnhub-writeups",
    ROOT / "bugforge-writeups",
    ROOT / "webverse-writeups",
    ROOT / "gensec",
    ROOT / "cooking",
    ROOT / "_template",
]

# Pattern that matches the existing inline nav block (and any preceding indentation).
# Both single-line and multi-line variants are covered by DOTALL + .*?
NAV_PATTERN = re.compile(
    r'[ \t]*<nav class="topnav">.*?</nav>',
    re.DOTALL,
)

# Pattern to detect an already-converted file
STUB_PATTERN = re.compile(r'<div id="nav"\s+data-nav-src=')


def stub_for(html_path: Path) -> str:
    """Return the per-page nav stub + script include with correct relative prefixes."""
    rel = html_path.parent.resolve().relative_to(ROOT.resolve())
    depth = 0 if str(rel) == "." else len(rel.parts)
    prefix = "../" * depth
    return (
        f'    <div id="nav" data-nav-src="{prefix}_includes/nav.html" data-nav-prefix="{prefix}"></div>\n'
        f'    <script src="{prefix}js/nav.js" defer></script>'
    )


def has_nav_script(content: str) -> bool:
    return 'src="' in content and "js/nav.js" in content


def convert(html_path: Path) -> str:
    content = html_path.read_text(encoding="utf-8")

    if STUB_PATTERN.search(content) and has_nav_script(content):
        return "already-converted"

    stub = stub_for(html_path)

    new_content, n = NAV_PATTERN.subn(stub, content, count=1)
    if n == 0:
        return "no-nav-found"

    html_path.write_text(new_content, encoding="utf-8")
    return "converted"


def main():
    counts = {"converted": 0, "already-converted": 0, "no-nav-found": 0}
    for d in TARGET_DIRS:
        if not d.exists():
            continue
        for html in sorted(d.glob("*.html")):
            result = convert(html)
            counts[result] = counts.get(result, 0) + 1
            if result == "no-nav-found":
                print(f"  no <nav class=\"topnav\"> in: {html.relative_to(ROOT)}")

    print()
    print("Summary:")
    for k, v in counts.items():
        if v:
            print(f"  {k:>20}: {v}")


if __name__ == "__main__":
    main()
