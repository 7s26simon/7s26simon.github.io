#!/usr/bin/env python3
"""
populate-tables.py — Rebuild category landing-page tables from the manifest.

Reads _scripts/manifest.csv plus the existing original-writeup rows on
each landing page, and writes a fresh <tbody> with everything in
descending date order (newest first).

Touches:
    hackthebox.html
    tryhackme.html
    vulnhub.html
    bugforge.html
    webverse.html
    general.html  (security blog)

Does NOT touch:
    quicklinks.html  (curated vuln-tagged list - left to user)
    index.html       (latest-lab card - handled separately)
"""

import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "_scripts" / "manifest.csv"

# Which landing page each dest maps to, and what its table looks like
LANDING_PAGE = {
    "htb-writeups":      ("hackthebox.html",  "HackTheBox Writeups", "Box Name"),
    "thm-writeups":      ("tryhackme.html",   "TryHackMe Writeups",  "Room Name"),
    "vulnhub-writeups":  ("vulnhub.html",     "Vulnhub Writeups",    "VM Name"),
    "bugforge-writeups": ("bugforge.html",    "BugForge Writeups",   "Lab"),
    "webverse-writeups": ("webverse.html",    "WebVerse Writeups",   "Lab"),
    "gensec":            ("general.html",     "Security Research",   "Topic"),
}

# Which destinations need a Platform column (pages where the platform
# is shown per-row instead of being implied by the page itself).
PLATFORM_COLUMN_FOR = {
    "bugforge-writeups": "BugForge",
    "webverse-writeups": "WebVerse",
}

# Original (pre-Medium) writeups that already exist on the landing pages.
# These get merged with the imported entries by date.
ORIGINALS = {
    "htb-writeups": [
        # (date, name, difficulty, href)
        ("2020-11-08", "Tabby",   "Easy", "htb-writeups/tabby.html"),
        ("2020-11-08", "Blunder", "Easy", "htb-writeups/blunder.html"),
        ("2020-06-20", "Servmon", "Easy", "htb-writeups/servmon.html"),
        ("2020-06-07", "Legacy",  "Easy", "htb-writeups/legacy.html"),
    ],
    "thm-writeups": [
        ("2020-06-29", "Dave's Blog",        "Hard",   "thm-writeups/davesblog.html"),
        ("2020-06-10", "Year of The Rabbit", "Medium", "thm-writeups/yotr.html"),
        ("2020-05-19", "Jack",               "Hard",   "thm-writeups/jack.html"),
        ("2020-05-01", "Lian-Yu",            "Easy",   "thm-writeups/lianyu.html"),
        ("2020-04-15", "Alfred",             "Easy",   "thm-writeups/alfred.html"),
        ("2020-03-01", "Gh0stcat",           "Easy",   "thm-writeups/ghostcat.html"),
    ],
    "vulnhub-writeups": [
        ("2020-07-10", "Vegeta",                 "Beginner",                "vulnhub-writeups/vegeta.html"),
        ("2020-06-07", "Sumo",                   "Beginner",                "vulnhub-writeups/sumo.html"),
        ("2020-05-15", "Geisha",                 "Beginner / Intermediate", "vulnhub-writeups/geisha.html"),
        ("2020-04-01", "Escalate My Privileges", "Easy",                    "vulnhub-writeups/emp-writeup.html"),
    ],
    "gensec": [
        ("2020-06-07", "HSTS",                   "gensec/hsts.html"),
        ("2020-05-01", "Hacker101's Micro CMS",  "gensec/hacker101.html"),
        ("2020-04-15", "JWT-Crack",              "gensec/jwt-cracker.html"),
    ],
}


def clean_title(title: str) -> str:
    """Strip noise from imported titles."""
    t = title
    # Collapse multiple spaces
    t = re.sub(r"\s+", " ", t).strip()
    return t


def build_tbody(dest: str, imported_rows: list) -> str:
    """Combine originals + imported into a single tbody, sorted by date desc."""
    rows = []
    if dest == "gensec":
        # gensec rows are (date, title, href)
        for d, t, h in ORIGINALS.get(dest, []):
            rows.append((d, t, "", h))  # difficulty blank for gensec
        for r in imported_rows:
            href = f"{dest}/{r['slug']}.html"
            rows.append((r["date"], clean_title(r["title"]), "", href))
    else:
        # platform rows are (date, name, difficulty, href)
        for d, n, diff, h in ORIGINALS.get(dest, []):
            rows.append((d, n, diff, h))
        for r in imported_rows:
            href = f"{dest}/{r['slug']}.html"
            rows.append((r["date"], clean_title(r["title"]), "-", href))

    # Sort: newest first
    rows.sort(key=lambda x: x[0] or "", reverse=True)

    lines = []
    if dest == "gensec":
        # gensec has 2 columns: Topic | Article
        for date, title, _, href in rows:
            lines.append(
                f'                <tr><td>{html_escape(title)}</td>'
                f'<td><a href="{href}" target="_blank">read</a></td></tr>'
            )
    elif dest in PLATFORM_COLUMN_FOR:
        # Lab | Platform | Date | Writeup
        platform = PLATFORM_COLUMN_FOR[dest]
        for date, name, diff, href in rows:
            lines.append(
                f'                <tr><td>{html_escape(name)}</td>'
                f'<td>{platform}</td>'
                f'<td>{date}</td>'
                f'<td><a href="{href}">read</a></td></tr>'
            )
    else:
        # platform pages have 3 columns: Name | Date | Writeup
        for date, name, diff, href in rows:
            lines.append(
                f'                <tr><td>{html_escape(name)}</td>'
                f'<td>{date}</td>'
                f'<td><a href="{href}">read</a></td></tr>'
            )
    return "\n".join(lines)


def html_escape(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def update_landing_page(landing_html: Path, dest: str, tbody_html: str, title_label: str):
    """Replace the existing <tbody>...</tbody> on the landing page."""
    content = landing_html.read_text(encoding="utf-8")

    # Build the right <thead> for this destination
    if dest == "gensec":
        new_thead = (
            "            <thead>\n"
            "                <tr>\n"
            "                    <th>Topic</th>\n"
            "                    <th>Article</th>\n"
            "                </tr>\n"
            "            </thead>"
        )
    elif dest in PLATFORM_COLUMN_FOR:
        new_thead = (
            "            <thead>\n"
            "                <tr>\n"
            f"                    <th>{title_label}</th>\n"
            "                    <th>Platform</th>\n"
            "                    <th>Date</th>\n"
            "                    <th>Writeup</th>\n"
            "                </tr>\n"
            "            </thead>"
        )
    else:
        new_thead = (
            "            <thead>\n"
            "                <tr>\n"
            f"                    <th>{title_label}</th>\n"
            "                    <th>Date</th>\n"
            "                    <th>Writeup</th>\n"
            "                </tr>\n"
            "            </thead>"
        )
    content = re.sub(
        r"<thead>.*?</thead>",
        new_thead,
        content,
        count=1,
        flags=re.DOTALL,
    )

    # Replace tbody
    new_tbody = "            <tbody>\n" + tbody_html + "\n            </tbody>"
    content, n = re.subn(
        r"<tbody>.*?</tbody>",
        new_tbody,
        content,
        count=1,
        flags=re.DOTALL,
    )
    if n == 0:
        print(f"  WARN: no <tbody> found in {landing_html}")
        return

    landing_html.write_text(content, encoding="utf-8")


def main():
    if not MANIFEST.exists():
        raise SystemExit(f"manifest not found: {MANIFEST}")

    with MANIFEST.open() as f:
        manifest = list(csv.DictReader(f))

    # Group manifest rows by dest
    by_dest = {}
    for row in manifest:
        d = row["dest"].strip()
        if not d:
            continue
        by_dest.setdefault(d, []).append(row)

    for dest, (page_name, _, title_label) in LANDING_PAGE.items():
        page_path = ROOT / page_name
        if not page_path.exists():
            print(f"skip (no page): {page_path}")
            continue
        imported = by_dest.get(dest, [])
        tbody = build_tbody(dest, imported)
        update_landing_page(page_path, dest, tbody, title_label)
        n_orig = len(ORIGINALS.get(dest, []))
        n_imp = len(imported)
        print(f"  {page_name}: {n_orig} original + {n_imp} imported = {n_orig + n_imp} rows")


if __name__ == "__main__":
    main()
