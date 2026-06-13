#!/usr/bin/env python3
"""
sync-nav.py - Render _includes/nav.html into every page's inline HTML.

How it works:
  - _includes/nav.html is the single source of truth (use data-href on internal links).
  - This script reads it, then for every .html page in the project:
      1. computes the correct relative prefix (e.g. ""  or "../")
      2. resolves each data-href to a real href with that prefix
      3. adds class="active" to whichever link/dropdown matches the page
      4. replaces the existing nav (whether inline <nav> or a JS stub)

Run this every time you edit _includes/nav.html.

Safe to re-run - it always replaces whichever nav form is currently in the file.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NAV_SRC = ROOT / "_includes" / "nav.html"

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

# When a writeup lives in one of these dirs, the matching dropdown item
# should be marked active.
DIR_TO_CATEGORY = {
    "htb-writeups":      "hackthebox.html",
    "thm-writeups":      "tryhackme.html",
    "vulnhub-writeups":  "vulnhub.html",
    "bugforge-writeups": "bugforge.html",
    "webverse-writeups": "webverse.html",
    "gensec":            "general.html",
}

# Top-level pages whose href == filename (used to mark active state directly).
# Anything else (writeups in subdirs, the template) falls back to dir-based active.

# Patterns we accept as the existing nav block to replace
NAV_INLINE_RE = re.compile(r'[ \t]*<nav class="topnav">.*?</nav>\n?', re.DOTALL)
NAV_STUB_RE = re.compile(
    r'[ \t]*<div id="nav"[^>]*></div>\s*<script src="[^"]*nav\.js"[^>]*></script>\n?',
    re.DOTALL,
)


def render_nav(template: str, prefix: str, active_file: str, active_dir: str) -> str:
    """Take the template nav HTML and resolve it for a specific page."""
    out = template

    # Resolve data-href -> href with prefix
    out = re.sub(
        r'data-href="([^"]+)"',
        lambda m: f'href="{prefix}{m.group(1)}"',
        out,
    )

    # Determine which file to mark active
    # Priority: explicit page match > category dir match > nothing
    active_targets = set()
    if active_file:
        active_targets.add(active_file.lower())
    if active_dir and active_dir in DIR_TO_CATEGORY:
        active_targets.add(DIR_TO_CATEGORY[active_dir].lower())

    # For each <a href="...">, if the path's filename matches an active target,
    # inject class="active" into the opening tag.
    def mark_active(m):
        full = m.group(0)
        href = m.group(1)
        filename = href.split("/")[-1].lower()
        if filename in active_targets:
            # add or merge class="active"
            if 'class="' in full:
                return re.sub(r'class="([^"]*)"', r'class="\1 active"', full, count=1)
            return full.replace("<a ", '<a class="active" ', 1)
        return full

    out = re.sub(r'<a\s+href="([^"]+)"[^>]*>', mark_active, out)

    # If the active item is inside the writeups dropdown, mark the dropdown parent too.
    writeups_categories = {"hackthebox.html", "tryhackme.html", "vulnhub.html", "bugforge.html", "webverse.html"}
    if active_targets & writeups_categories:
        out = out.replace(
            '<div class="topnav-dropdown">',
            '<div class="topnav-dropdown active">',
            1,
        )

    return out


def page_context(html_path: Path):
    """Return (prefix, active_file, active_dir) for a given HTML page."""
    rel = html_path.parent.resolve().relative_to(ROOT.resolve())
    depth = 0 if str(rel) == "." else len(rel.parts)
    prefix = "../" * depth

    if depth == 0:
        return prefix, html_path.name, None
    # Inside a subdir
    return prefix, None, rel.parts[0]


def sync_file(html_path: Path, template: str) -> str:
    prefix, active_file, active_dir = page_context(html_path)
    rendered = render_nav(template, prefix, active_file or "", active_dir or "")
    # Indent every line for visual consistency
    rendered_indented = "\n".join("    " + line if line.strip() else line for line in rendered.split("\n")).rstrip() + "\n"

    content = html_path.read_text(encoding="utf-8")
    new_content, n_inline = NAV_INLINE_RE.subn(rendered_indented, content, count=1)
    if n_inline == 0:
        new_content, n_stub = NAV_STUB_RE.subn(rendered_indented, content, count=1)
        if n_stub == 0:
            return "no-nav-found"

    if new_content != content:
        html_path.write_text(new_content, encoding="utf-8")
        return "updated"
    return "no-change"


def main():
    if not NAV_SRC.exists():
        raise SystemExit(f"nav template missing: {NAV_SRC}")
    template = NAV_SRC.read_text(encoding="utf-8").strip()

    counts = {"updated": 0, "no-change": 0, "no-nav-found": 0}
    for d in TARGET_DIRS:
        if not d.exists():
            continue
        for html in sorted(d.glob("*.html")):
            result = sync_file(html, template)
            counts[result] = counts.get(result, 0) + 1
            if result == "no-nav-found":
                print(f"  no nav block found: {html.relative_to(ROOT)}")

    print()
    print("Summary:")
    for k, v in counts.items():
        if v:
            print(f"  {k:>15}: {v}")


if __name__ == "__main__":
    main()
