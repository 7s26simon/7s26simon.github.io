#!/usr/bin/env python3
"""
strip-platform-from-labs.py - Remove 'BugForge', 'Bugforge.io', 'WebVerse',
'WebVerse-pro.com' etc. from lab names and file slugs in bugforge-writeups/
and webverse-writeups/.

Operations:
    1. For each .html in those two dirs, compute a cleaned slug + cleaned title.
    2. Rename HTML file -> new slug.
    3. Rename matching images/<slug>/ folder.
    4. Rewrite internal <img src="images/<slug>/..."> paths.
    5. Rewrite <title>...</title> and <div id="writeup-box-name"><p>...</p></div>.
    6. Update _scripts/manifest.csv (slug + title columns).
    7. Re-run populate-tables.py and update-quicklinks.py.

Safe to re-run - already-cleaned slugs are no-ops.
"""

import csv
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "_scripts" / "manifest.csv"

DIRS = ["bugforge-writeups", "webverse-writeups"]

# Slug-side: strip these tokens (each may appear at the end, before any
# 8-hex disambiguator suffix). Multiple passes handle stacked occurrences.
SLUG_PLATFORM_TOKENS = (
    "bugforge-io",
    "bugforge",
    "webverse-pro-com",
    "webverse-pro",
    "webverse",
)

# Title-side: strip these patterns (case-insensitive).
TITLE_STRIP_PATTERNS = [
    # parenthesised platform tags anywhere in the title
    re.compile(r"\s*\(\s*BugForge(?:\.io)?\s*\)", re.I),
    re.compile(r"\s*\(\s*WebVerse(?:-Pro\.com|-Pro)?\s*\)", re.I),
    # ' - WebVerse' / ' - BugForge' segments (with surrounding whitespace/dash)
    re.compile(r"\s*[-–—]\s*BugForge(?:\.io)?", re.I),
    re.compile(r"\s*[-–—]\s*WebVerse(?:-Pro\.com|-Pro)?", re.I),
    # bare platform word anywhere in title (with at least one space boundary on either side)
    re.compile(r"\s+BugForge(?:\.io)?\b", re.I),
    re.compile(r"\s+WebVerse(?:-Pro\.com|-Pro)?\b", re.I),
]


def clean_slug(slug: str) -> str:
    """Strip platform tokens, preserving any 8-hex disambiguator at the end."""
    # Detect trailing 8-hex-character collision suffix and preserve it
    m = re.match(r"^(.+)-([0-9a-f]{8})$", slug)
    if m:
        base, hash_part = m.group(1), m.group(2)
        new_base = _strip_platform_tokens_from_slug(base)
        return f"{new_base}-{hash_part}" if new_base else f"writeup-{hash_part}"
    return _strip_platform_tokens_from_slug(slug) or "writeup"


def _strip_platform_tokens_from_slug(s: str) -> str:
    # Strip platform tokens anywhere in the slug (between dashes or at boundaries).
    # Loop until stable in case of stacked tokens.
    while True:
        original = s
        for tok in SLUG_PLATFORM_TOKENS:
            # (^|-) before, (-|$) after; lookahead so the trailing dash stays available
            s = re.sub(rf"(?:^|-){re.escape(tok)}(?=-|$)", "", s, flags=re.I)
        # collapse double dashes from removals, strip edge dashes
        s = re.sub(r"-+", "-", s).strip("-")
        if s == original:
            return s


def clean_title(title: str) -> str:
    t = title
    for _ in range(5):
        new = t
        for p in TITLE_STRIP_PATTERNS:
            new = p.sub(" ", new)
        # collapse multiple spaces
        new = re.sub(r"\s+", " ", new)
        # strip dangling separator chars at ends
        new = new.strip(" -,.")
        # also strip trailing "()" if a paren was emptied
        new = re.sub(r"\(\s*\)", "", new).strip(" -,.")
        if new == t:
            break
        t = new
    return t.strip()


def main():
    if not MANIFEST.exists():
        sys.exit(f"manifest not found: {MANIFEST}")

    # Load manifest into a slug-keyed dict for the dirs we care about
    with MANIFEST.open() as f:
        rows = list(csv.DictReader(f))

    # Build the rename plan
    plan = []  # list of dicts: dest, old_slug, new_slug, old_title, new_title, row_ref
    for r in rows:
        dest = r["dest"].strip()
        if dest not in DIRS:
            continue
        old_slug = r["slug"]
        new_slug = clean_slug(old_slug)
        old_title = r["title"]
        new_title = clean_title(old_title)
        if old_slug == new_slug and old_title == new_title:
            continue
        plan.append({
            "dest": dest,
            "old_slug": old_slug,
            "new_slug": new_slug,
            "old_title": old_title,
            "new_title": new_title,
            "row": r,
        })

    # Check for collisions in new slugs
    new_paths = {}
    for p in plan:
        key = (p["dest"], p["new_slug"])
        if key in new_paths:
            sys.exit(
                f"Slug collision after cleanup: {p['old_slug']} and "
                f"{new_paths[key]['old_slug']} both -> {p['new_slug']}"
            )
        new_paths[key] = p

    # Also check against existing rows that weren't renamed (their slug is unchanged)
    for r in rows:
        d = r["dest"].strip()
        if d not in DIRS:
            continue
        if (d, r["slug"]) in new_paths:
            # Either this row IS one being renamed (key matches its own new_slug), or
            # an un-renamed row collides with a renamed one.
            entry = new_paths[(d, r["slug"])]
            if entry["row"] is r:
                continue  # same row
            sys.exit(
                f"Slug collision: cleaning {entry['old_slug']} would clash with "
                f"existing {r['slug']} in {d}"
            )

    print(f"Renaming {len(plan)} writeups:")
    for p in plan[:5]:
        print(f"  {p['old_slug']} -> {p['new_slug']}")
        print(f"    {p['old_title']!r}")
        print(f"    -> {p['new_title']!r}")
    if len(plan) > 5:
        print(f"  ... and {len(plan) - 5} more")
    print()

    # --- execute rename plan ---
    for p in plan:
        dest_dir = ROOT / p["dest"]
        old_html = dest_dir / f"{p['old_slug']}.html"
        new_html = dest_dir / f"{p['new_slug']}.html"
        old_img = dest_dir / "images" / p["old_slug"]
        new_img = dest_dir / "images" / p["new_slug"]

        # 1) rename the image folder so the new path exists when we patch HTML
        if old_img.exists() and old_img != new_img:
            if new_img.exists():
                # merge - very unlikely with the collision check above
                for f in old_img.iterdir():
                    target = new_img / f.name
                    if not target.exists():
                        shutil.move(str(f), str(target))
                old_img.rmdir()
            else:
                shutil.move(str(old_img), str(new_img))

        # 2) read HTML, patch internal references
        if not old_html.exists():
            print(f"  WARN: {old_html} missing; skipping HTML patch")
            continue
        content = old_html.read_text(encoding="utf-8")

        # rewrite image src paths
        if p["old_slug"] != p["new_slug"]:
            content = content.replace(
                f'src="images/{p["old_slug"]}/',
                f'src="images/{p["new_slug"]}/',
            )

        # rewrite <title>
        old_title_safe = re.escape(p["old_title"])
        content = re.sub(
            r"<title>[^<]*</title>",
            f"<title>{html_escape(p['new_title'])} // 7s26simon</title>",
            content,
            count=1,
        )

        # rewrite writeup-box-name (the heading shown at top of the writeup)
        content = re.sub(
            r'(<div id="writeup-box-name">\s*<p>)[^<]*(</p>\s*</div>)',
            lambda m: m.group(1) + html_escape(p["new_title"]) + m.group(2),
            content,
            count=1,
            flags=re.DOTALL,
        )

        # write to new location, remove old if different
        new_html.write_text(content, encoding="utf-8")
        if old_html != new_html:
            old_html.unlink()

    # --- update manifest ---
    for p in plan:
        p["row"]["slug"] = p["new_slug"]
        p["row"]["title"] = p["new_title"]

    with MANIFEST.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["filename", "slug", "title", "date", "suggested_dest", "dest"],
        )
        w.writeheader()
        w.writerows(rows)

    print(f"Updated {MANIFEST}")

    # --- re-run downstream regenerators ---
    print()
    print("Running populate-tables.py ...")
    subprocess.run([sys.executable, "_scripts/populate-tables.py"], cwd=str(ROOT), check=True)

    print()
    print("Running tag-vulns.py ...")
    subprocess.run([sys.executable, "_scripts/tag-vulns.py"], cwd=str(ROOT), check=True)

    print()
    print("Running update-quicklinks.py ...")
    subprocess.run([sys.executable, "_scripts/update-quicklinks.py"], cwd=str(ROOT), check=True)


def html_escape(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


if __name__ == "__main__":
    main()
