#!/usr/bin/env python3
"""
add-writeup.py - Add a new writeup entry and rebuild quicklinks.html.

Usage:
  python3 _scripts/add-writeup.py \
    --name "Tamper Temple" \
    --dest webverse-writeups \
    --slug tamper-temple-hard \
    --vulns "sqli xss" \
    --date 2026-06-13

  python3 _scripts/add-writeup.py --rollback

  --name   Display name for the lab / machine
  --dest   Destination folder: htb-writeups | thm-writeups | vulnhub-writeups |
                               bugforge-writeups | webverse-writeups | gensec
  --slug   HTML filename without the .html extension (must match actual file)
  --vulns  Space- or comma-separated vulnerability tags (see VALID_TAGS below)
  --date   Date in YYYY-MM-DD format (defaults to today)

  --rollback  Undo the last add (restores vuln-tags.csv and index.html, rebuilds quicklinks)

Valid vulnerability tags:
  sqli, xss, sxss, rxss, stored-xss, xxe, ssrf, ssti, lfi, rfi, path-traversal,
  rce, command-injection, idor, access-control, bfla, bola, broken-auth,
  weak-auth, jwt, csrf, graphql, websockets, business-logic, race-condition,
  nosql, upload, deserialization, prototype-pollution, open-redirect,
  steganography, git-exposure, logic-flaw, otp-bypass, mfa-bypass,
  priv-esc, api-abuse, mass-assignment

After adding, this script rebuilds quicklinks.html automatically.
"""

import argparse
import csv
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT          = Path(__file__).resolve().parent.parent
VULN_TAGS_CSV = ROOT / "_scripts" / "vuln-tags.csv"
INDEX_HTML    = ROOT / "index.html"
BACKUP_DIR    = ROOT / "_scripts" / ".rollback"

DEST_TO_PLATFORM = {
    "htb-writeups":      ("HackTheBox", "platform-htb"),
    "thm-writeups":      ("TryHackMe",  "platform-thm"),
    "vulnhub-writeups":  ("Vulnhub",    "platform-vh"),
    "bugforge-writeups": ("BugForge",   "platform-bf"),
    "webverse-writeups": ("WebVerse",   "platform-wv"),
    "gensec":            ("Blog",       "platform-bf"),
}

VALID_TAGS = {
    "sqli", "xss", "sxss", "rxss", "stored-xss", "xxe", "ssrf", "ssti",
    "lfi", "rfi", "path-traversal", "rce", "command-injection",
    "idor", "access-control", "bfla", "bola", "broken-auth", "weak-auth",
    "jwt", "csrf", "graphql", "websockets", "business-logic", "race-condition",
    "nosql", "upload", "deserialization", "prototype-pollution", "open-redirect",
    "steganography", "git-exposure", "logic-flaw", "otp-bypass", "mfa-bypass",
    "priv-esc", "api-abuse", "mass-assignment",
}

VALID_DESTS = {
    "htb-writeups", "thm-writeups", "vulnhub-writeups",
    "bugforge-writeups", "webverse-writeups", "gensec",
}


# ---------------------------------------------------------------------------
# Backup / rollback
# ---------------------------------------------------------------------------

def save_backup():
    BACKUP_DIR.mkdir(exist_ok=True)
    for src in (VULN_TAGS_CSV, INDEX_HTML):
        if src.exists():
            (BACKUP_DIR / src.name).write_bytes(src.read_bytes())


def rollback():
    if not BACKUP_DIR.exists():
        print("No rollback data found - nothing to undo.")
        sys.exit(1)

    restored = []
    for name in ("vuln-tags.csv", "index.html"):
        bak = BACKUP_DIR / name
        if not bak.exists():
            print(f"  Missing backup for {name}, skipping.")
            continue
        dst = ROOT / "_scripts" / name if name.endswith(".csv") else ROOT / name
        dst.write_bytes(bak.read_bytes())
        restored.append(name)

    if not restored:
        print("Nothing restored.")
        sys.exit(1)

    print(f"Restored: {', '.join(restored)}")
    print("Rebuilding quicklinks.html...")
    rebuild_quicklinks()
    # Remove backup so you can't roll back twice
    for f in BACKUP_DIR.iterdir():
        f.unlink()
    BACKUP_DIR.rmdir()
    print("Rollback complete.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def slugify(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def parse_vulns(raw: str) -> str:
    tags = re.split(r"[,\s]+", raw.strip())
    tags = [t.lower().strip() for t in tags if t.strip()]
    unknown = [t for t in tags if t not in VALID_TAGS]
    if unknown:
        print(f"Warning: unrecognised tag(s): {', '.join(unknown)}")
        print(f"Valid tags: {', '.join(sorted(VALID_TAGS))}")
        sys.exit(1)
    return " ".join(tags)


def load_existing_slugs() -> set:
    if not VULN_TAGS_CSV.exists():
        return set()
    with VULN_TAGS_CSV.open(newline="", encoding="utf-8") as f:
        return {row["slug"] for row in csv.DictReader(f)}


def append_row(slug: str, dest: str, name: str, entry_date: str, vulns: str):
    rows = []
    if VULN_TAGS_CSV.exists():
        with VULN_TAGS_CSV.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))

    rows.append({
        "slug":       slug,
        "dest":       dest,
        "title":      name,
        "date":       entry_date,
        "categories": vulns,
    })

    with VULN_TAGS_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["slug", "dest", "title", "date", "categories"])
        writer.writeheader()
        writer.writerows(rows)


def update_latest_lab(slug: str, dest: str, name: str, entry_date: str):
    platform_name, platform_class = DEST_TO_PLATFORM.get(dest, ("Unknown", "platform-bf"))
    href = f"{dest}/{slug}.html"

    try:
        from datetime import datetime
        d = datetime.strptime(entry_date, "%Y-%m-%d")
        display_date = d.strftime("%-d %B %Y")
    except Exception:
        display_date = entry_date

    new_card = (
        f'            <div class="latest-grid latest-grid-single">\n'
        f'                <a href="{href}" class="latest-card">\n'
        f'                    <span class="latest-platform {platform_class}">{platform_name}</span>\n'
        f'                    <span class="latest-name">{name}</span>\n'
        f'                </a>\n'
        f'            </div>'
    )

    content = INDEX_HTML.read_text(encoding="utf-8")

    content = re.sub(
        r'// latest (?:lab|writeup) <span class="latest-date">\([^)]*\)</span>',
        f'// latest writeup <span class="latest-date">({display_date})</span>',
        content,
    )
    content = re.sub(
        r'[ \t]*<div class="latest-grid latest-grid-single">.*?</div>',
        new_card,
        content,
        flags=re.DOTALL,
    )

    INDEX_HTML.write_text(content, encoding="utf-8")


def rebuild_quicklinks():
    script = ROOT / "_scripts" / "update-quicklinks.py"
    result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
    if result.returncode != 0:
        print("Error rebuilding quicklinks.html:")
        print(result.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Add a writeup to vuln-tags.csv and rebuild quicklinks.html"
    )
    parser.add_argument("--rollback", action="store_true", help="Undo the last add")
    parser.add_argument("--name",  help="Display name for the lab / machine")
    parser.add_argument("--dest",  choices=sorted(VALID_DESTS),
                        help="Destination folder (e.g. webverse-writeups)")
    parser.add_argument("--slug",  help="HTML filename without .html (auto-derived from --name if omitted)")
    parser.add_argument("--vulns", default="", help="Space/comma-separated vulnerability tags")
    parser.add_argument("--date",  default=str(date.today()), help="Date YYYY-MM-DD (default: today)")
    args = parser.parse_args()

    if args.rollback:
        rollback()
        return

    if not args.name or not args.dest:
        parser.error("--name and --dest are required unless using --rollback")

    slug  = args.slug if args.slug else slugify(args.name)
    vulns = parse_vulns(args.vulns) if args.vulns else ""

    html_path = ROOT / args.dest / f"{slug}.html"
    if not html_path.exists():
        print(f"Warning: {html_path.relative_to(ROOT)} does not exist.")
        print("  The entry will still be added, but the link will be broken until you create the file.")

    existing = load_existing_slugs()
    if slug in existing:
        print(f"Error: slug '{slug}' already exists in vuln-tags.csv")
        print("  Use --slug to specify a unique slug.")
        sys.exit(1)

    # Save backup before making any changes
    save_backup()

    append_row(slug, args.dest, args.name, args.date, vulns)
    print(f"Added: [{args.date}] {args.name}  ({args.dest}/{slug}.html)")
    if vulns:
        print(f"  Tags: {vulns}")

    print("Rebuilding quicklinks.html...")
    rebuild_quicklinks()

    print("Updating latest writeup on homepage...")
    update_latest_lab(slug, args.dest, args.name, args.date)

    print("Done.  (Run with --rollback to undo.)")


if __name__ == "__main__":
    main()
