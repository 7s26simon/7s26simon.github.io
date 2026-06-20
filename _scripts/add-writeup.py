#!/usr/bin/env python3
"""
add-writeup.py - Interactive writeup builder.

Creates the HTML file from the template, creates an images folder, starts a
local preview server, opens the browser, lets you build content interactively
(saving after every action so the browser auto-refreshes), then registers the
writeup in vuln-tags.csv, rebuilds writeups.html, updates the homepage, and
runs sync-nav.

Usage:
  python3 _scripts/add-writeup.py
  python3 _scripts/add-writeup.py --rollback

Valid vulnerability tags:
  sqli, xss, sxss, rxss, stored-xss, xxe, ssrf, ssti, lfi, rfi, path-traversal,
  rce, command-injection, idor, access-control, bfla, bola, broken-auth,
  weak-auth, jwt, csrf, graphql, websockets, business-logic, race-condition,
  nosql, upload, deserialization, prototype-pollution, open-redirect,
  steganography, git-exposure, logic-flaw, otp-bypass, mfa-bypass,
  priv-esc, api-abuse, mass-assignment
"""

import argparse
import csv
import re
import shutil
import subprocess
import sys
import time
import webbrowser
from datetime import date, datetime
from pathlib import Path

ROOT          = Path(__file__).resolve().parent.parent
TEMPLATE_HTML = ROOT / "_template" / "writeup-template.html"
VULN_TAGS_CSV = ROOT / "_scripts" / "vuln-tags.csv"
INDEX_HTML    = ROOT / "index.html"
BACKUP_DIR    = ROOT / "_scripts" / ".rollback"
PREVIEW_PORT  = 8080

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

TAG_DISPLAY = {
    "sqli":                 "SQL Injection (SQLi)",
    "xss":                  "Cross-Site Scripting (XSS)",
    "sxss":                 "Stored XSS",
    "rxss":                 "Reflected XSS",
    "stored-xss":           "Stored XSS",
    "xxe":                  "XML External Entity (XXE)",
    "ssrf":                 "Server-Side Request Forgery (SSRF)",
    "ssti":                 "Server-Side Template Injection (SSTI)",
    "lfi":                  "Local File Inclusion (LFI)",
    "rfi":                  "Remote File Inclusion (RFI)",
    "path-traversal":       "Path Traversal",
    "rce":                  "Remote Code Execution (RCE)",
    "command-injection":    "Command Injection",
    "idor":                 "Insecure Direct Object Reference (IDOR)",
    "access-control":       "Broken Access Control",
    "bfla":                 "Broken Function Level Authorisation (BFLA)",
    "bola":                 "Broken Object Level Authorisation (BOLA)",
    "broken-auth":          "Broken Authentication",
    "weak-auth":            "Weak Authentication",
    "jwt":                  "JWT Vulnerability",
    "csrf":                 "Cross-Site Request Forgery (CSRF)",
    "graphql":              "GraphQL Injection",
    "websockets":           "WebSockets Vulnerability",
    "business-logic":       "Business Logic Flaw",
    "race-condition":       "Race Condition",
    "nosql":                "NoSQL Injection",
    "upload":               "Unrestricted File Upload",
    "deserialization":      "Insecure Deserialization",
    "prototype-pollution":  "Prototype Pollution",
    "open-redirect":        "Open Redirect",
    "steganography":        "Steganography",
    "git-exposure":         "Git Exposure",
    "logic-flaw":           "Logic Flaw",
    "otp-bypass":           "OTP Bypass",
    "mfa-bypass":           "MFA Bypass",
    "priv-esc":             "Privilege Escalation",
    "api-abuse":            "API Abuse",
    "mass-assignment":      "Mass Assignment",
}

DESTINATIONS = {
    "1": "bugforge-writeups",
    "2": "htb-writeups",
    "3": "thm-writeups",
    "4": "vulnhub-writeups",
    "5": "webverse-writeups",
}

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

# Auto-refresh meta tag injected during preview, removed on final save
_AUTO_REFRESH = '    <meta http-equiv="refresh" content="2">\n'


# ---------------------------------------------------------------------------
# Backup / rollback
# ---------------------------------------------------------------------------

def save_backup(slug: str, dest_name: str):
    BACKUP_DIR.mkdir(exist_ok=True)
    for src in (VULN_TAGS_CSV, INDEX_HTML):
        if src.exists():
            (BACKUP_DIR / src.name).write_bytes(src.read_bytes())
    (BACKUP_DIR / "created.txt").write_text(f"{dest_name}/{slug}", encoding="utf-8")


def rollback():
    if not BACKUP_DIR.exists():
        print("No rollback data found — nothing to undo.")
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

    created_txt = BACKUP_DIR / "created.txt"
    if created_txt.exists():
        created  = created_txt.read_text(encoding="utf-8").strip()
        dest_name, slug = created.split("/", 1)
        html_file  = ROOT / dest_name / f"{slug}.html"
        images_dir = ROOT / dest_name / "images" / slug

        if html_file.exists():
            html_file.unlink()
            print(f"Deleted: {html_file.relative_to(ROOT)}")

        if images_dir.exists():
            shutil.rmtree(images_dir)
            print(f"Deleted: {images_dir.relative_to(ROOT)}/")

    print("Rebuilding writeups.html...")
    rebuild_writeups()

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
    if not raw.strip():
        return ""
    tags = re.split(r"[,\s]+", raw.strip())
    tags = [t.lower().strip() for t in tags if t.strip()]
    unknown = [t for t in tags if t not in VALID_TAGS]
    if unknown:
        print(f"  Unrecognised tag(s): {', '.join(unknown)}")
        print(f"  Valid tags: {', '.join(sorted(VALID_TAGS))}")
        return None
    return " ".join(tags)


def load_existing_slugs() -> set:
    if not VULN_TAGS_CSV.exists():
        return set()
    with VULN_TAGS_CSV.open(newline="", encoding="utf-8") as f:
        return {row["slug"] for row in csv.DictReader(f)}


def append_csv_row(slug: str, dest: str, name: str, entry_date: str, vulns: str):
    rows = []
    if VULN_TAGS_CSV.exists():
        with VULN_TAGS_CSV.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    rows.append({"slug": slug, "dest": dest, "title": name,
                 "date": entry_date, "categories": vulns})
    with VULN_TAGS_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["slug", "dest", "title", "date", "categories"])
        writer.writeheader()
        writer.writerows(rows)


def update_homepage(slug: str, dest: str, name: str, entry_date: str):
    platform_name, platform_class = DEST_TO_PLATFORM.get(dest, ("Unknown", "platform-bf"))
    href = f"{dest}/{slug}.html"
    try:
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
        r'latest (?:lab|writeup) <span class="latest-date">\([^)]*\)</span>',
        f'latest writeup <span class="latest-date">({display_date})</span>',
        content,
    )
    content = re.sub(
        r'[ \t]*<div class="latest-grid latest-grid-single">.*?</div>',
        new_card,
        content,
        flags=re.DOTALL,
    )
    INDEX_HTML.write_text(content, encoding="utf-8")


def rebuild_writeups():
    script = ROOT / "_scripts" / "update-writeups.py"
    result = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
    if result.returncode != 0:
        print("Error rebuilding writeups.html:")
        print(result.stderr)
        sys.exit(1)


def run_sync_nav():
    sync = ROOT / "_scripts" / "sync-nav.py"
    subprocess.run([sys.executable, str(sync)], capture_output=True)


# ---------------------------------------------------------------------------
# Preview server
# ---------------------------------------------------------------------------

def start_preview_server():
    """Start python -m http.server in the background, serving from ROOT."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(PREVIEW_PORT),
         "--directory", str(ROOT)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc


# ---------------------------------------------------------------------------
# HTML file helpers
# ---------------------------------------------------------------------------

def prepare_shell(display_name: str) -> str:
    """Read and prep the template — strip comments, replace MACHINE_NAME.
    Returns html string with empty #marg-asthetic content ready for injection."""
    html = TEMPLATE_HTML.read_text(encoding="utf-8")
    html = re.sub(r"\s*<!--\s*={4,}.*?WRITEUP TEMPLATE.*?={4,}\s*-->", "", html, flags=re.DOTALL)
    html = re.sub(r"\s*<!-- ===== Hero.*?</div>", "", html, flags=re.DOTALL)
    html = re.sub(r"\s*<!-- ===== Main writeup body ===== -->", "", html)
    html = html.replace("MACHINE_NAME", display_name)
    return html


def write_html(out_path: Path, shell: str, blocks: list, preview: bool):
    """Inject blocks into shell and write to disk.
    preview=True adds auto-refresh meta tag; preview=False strips it."""
    body = "\n".join(blocks)
    html = re.sub(
        r'(<div id="marg-asthetic">).*?(\s+<hr>\s+<p>&#x1F37A;)',
        rf"\1\n\n{body}\n\n        \2",
        shell,
        flags=re.DOTALL,
    )
    if preview:
        html = html.replace("<meta charset=\"UTF-8\">",
                            "<meta charset=\"UTF-8\">\n" + _AUTO_REFRESH.rstrip())
    out_path.write_text(html, encoding="utf-8")


# ---------------------------------------------------------------------------
# Interactive content builder
# ---------------------------------------------------------------------------

def numbered_screenshots(images_dir: Path) -> list:
    if not images_dir.exists():
        return []
    files = [
        f for f in images_dir.iterdir()
        if f.suffix.lower() in IMAGE_EXTS and re.match(r"^\d+$", f.stem)
    ]
    return sorted(files, key=lambda f: int(f.stem))


def img_tag(slug: str, fname: str) -> str:
    return f'        <img src="images/{slug}/{fname}" alt="{fname}">'


def build_content(slug: str, images_dir: Path, platform: str,
                  target_url: str, vuln_classes: str,
                  out_path: Path, shell: str) -> list:

    blocks = [
        f'        <p>',
        f'            <strong>Platform:</strong> {platform}<br>',
        f'            <strong>Target:</strong> {target_url}<br>',
        f'            <strong>Vulnerability classes:</strong> {vuln_classes}',
        f'        </p>',
        "",
        img_tag(slug, f"{slug}.png"),
        "",
    ]

    # Write initial preview file
    write_html(out_path, shell, blocks, preview=True)

    shots = numbered_screenshots(images_dir)
    img_hint = (", ".join(f.name for f in shots)
                if shots else "(none yet — drop images in the folder and they'll appear)")

    print(f"\nScreenshots available: {img_hint}")
    print("─" * 60)

    section_counter = [1]

    while True:
        print("\n  1) Write a paragraph")
        print("  2) Add a screenshot")
        print("  3) Add a section heading (h2)")
        print("  s) Save and finish")
        action = input("\n> ").strip().lower()

        if action == "1":
            text = input("  Paragraph: ").strip()
            if text:
                blocks.append("        <br>")
                blocks.append(f"        <p>{text}</p>")
                blocks.append("")
                write_html(out_path, shell, blocks, preview=True)
                print("  ✓ Paragraph added.")

        elif action == "2":
            shots = numbered_screenshots(images_dir)
            if shots:
                print("  Available: " + "  ".join(f.name for f in shots))
            fname = input("  Screenshot filename (e.g. 1.png): ").strip()
            if fname:
                blocks.append(img_tag(slug, fname))
                blocks.append("")
                write_html(out_path, shell, blocks, preview=True)
                print(f"  ✓ {fname} added.")

        elif action == "3":
            heading = input("  Section heading (e.g. Overview): ").strip()
            if heading:
                n = section_counter[0]
                blocks.append(f"        <h2>{n}. {heading}</h2>")
                blocks.append("")
                section_counter[0] += 1
                write_html(out_path, shell, blocks, preview=True)
                print(f"  ✓ <h2>{n}. {heading}</h2> added.")

        elif action == "s":
            confirm = input("  Are you sure you want to save and finish? (y/n): ").strip().lower()
            if confirm == "y":
                break
            print("  Continuing...")

        else:
            print("  Please enter 1, 2, 3, or s.")

    return blocks


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Interactive writeup builder")
    parser.add_argument("--rollback", action="store_true", help="Undo the last add")
    args = parser.parse_args()

    if args.rollback:
        rollback()
        return

    # ── Lab name ──────────────────────────────────────────────────────────────
    raw_name = input("Lab name (e.g. Milk and Honey): ").strip()
    if not raw_name:
        print("Error: name cannot be empty.")
        sys.exit(1)

    slug = slugify(raw_name)
    print(f"  Filename: {slug}.html")

    existing = load_existing_slugs()
    if slug in existing:
        print(f"Error: '{slug}' already exists in vuln-tags.csv.")
        sys.exit(1)

    # ── Destination ───────────────────────────────────────────────────────────
    print("\nWhere should the writeup go?")
    for key, folder in DESTINATIONS.items():
        print(f"  {key}) {folder}")

    choice = input("\nEnter 1-5: ").strip()
    if choice not in DESTINATIONS:
        print("Error: enter a number between 1 and 5.")
        sys.exit(1)

    dest_name   = DESTINATIONS[choice]
    dest_folder = ROOT / dest_name
    images_dir  = dest_folder / "images" / slug
    out_path    = dest_folder / f"{slug}.html"

    if out_path.exists():
        print(f"Error: {dest_name}/{slug}.html already exists.")
        sys.exit(1)

    # ── Create images folder ──────────────────────────────────────────────────
    images_dir.mkdir(parents=True, exist_ok=True)
    print(f"\nCreated: {images_dir.relative_to(ROOT)}/")

    # ── Target URL ────────────────────────────────────────────────────────────
    target_url = input("\nTarget URL (e.g. https://lab.example.com): ").strip()

    # ── Vulnerability tags ────────────────────────────────────────────────────
    print(f"\nVulnerability tags (space or comma separated, or leave blank):")
    print(f"  {', '.join(sorted(VALID_TAGS))}")
    while True:
        raw_vulns = input("\nTags: ").strip()
        vulns = parse_vulns(raw_vulns)
        if vulns is not None:
            break
        print("  Please re-enter tags.")

    platform_display = DEST_TO_PLATFORM.get(dest_name, ("Unknown", ""))[0]
    vuln_classes = ", ".join(
        TAG_DISPLAY.get(t, t.upper()) for t in vulns.split()
    ) if vulns else ""

    # ── Start preview server and open browser ─────────────────────────────────
    shell = prepare_shell(raw_name)
    server = start_preview_server()
    time.sleep(0.8)  # give the server a moment to bind
    preview_url = f"http://localhost:{PREVIEW_PORT}/{dest_name}/{slug}.html"
    webbrowser.open(preview_url)
    print(f"\nPreview: {preview_url}  (auto-refreshes every 2s)")

    # ── Build content interactively ───────────────────────────────────────────
    print(f"Building content for {slug}.html")
    blocks = build_content(slug, images_dir, platform_display, target_url,
                           vuln_classes, out_path, shell)

    # ── Stop preview server ───────────────────────────────────────────────────
    server.terminate()

    # ── Final save (no auto-refresh tag) ─────────────────────────────────────
    write_html(out_path, shell, blocks, preview=False)
    print(f"\nSaved: {out_path.relative_to(ROOT)}")

    # ── Register and rebuild ──────────────────────────────────────────────────
    save_backup(slug, dest_name)

    entry_date = str(date.today())
    append_csv_row(slug, dest_name, raw_name, entry_date, vulns)
    print("Registered in vuln-tags.csv")

    print("Rebuilding writeups.html...")
    rebuild_writeups()

    print("Updating homepage...")
    update_homepage(slug, dest_name, raw_name, entry_date)

    print("Running sync-nav...")
    run_sync_nav()

    print(f"\nDone. (Run with --rollback to undo.)")


if __name__ == "__main__":
    main()
