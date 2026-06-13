#!/usr/bin/env python3
"""
import-medium.py - Import Medium export posts into this site.

Two-step workflow:

  1. python3 _scripts/import-medium.py init
       Scans ./posts/, writes _scripts/manifest.csv with one row per post:
         filename, slug, title, date, suggested_dest, dest
       Auto-suggests a destination based on the post title (TryHackMe,
       WebVerse, BugForge). Posts that look like Medium comments are
       left with an empty suggestion - you can leave them blank to skip.

  2. (edit _scripts/manifest.csv if needed - blank out rows you don't
     want, adjust 'dest' for misclassified ones)

  3. python3 _scripts/import-medium.py import
       Reads the manifest and for every row with a non-empty 'dest':
         - parses the Medium HTML
         - downloads all images to <dest>/images/<slug>/
         - rewrites <img src> to point local
         - strips Medium classes, signup blocks, buymeacoffee links
         - drops content into _template/writeup-template.html
         - writes <dest>/<slug>.html

Re-running 'import' is safe - already-downloaded images are reused and
existing output files are skipped unless --force is passed.

Requires: python3, beautifulsoup4 (pip3 install --user beautifulsoup4)
"""

import argparse
import csv
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

try:
    from bs4 import BeautifulSoup, NavigableString, Tag
except ImportError:
    sys.exit(
        "BeautifulSoup not installed.\n"
        "Install with one of:\n"
        "    pip3 install --user beautifulsoup4\n"
        "    pip3 install --break-system-packages --user beautifulsoup4"
    )

ROOT = Path(__file__).resolve().parent.parent
POSTS_DIR = ROOT / "posts"
MANIFEST = ROOT / "_scripts" / "manifest.csv"
TEMPLATE = ROOT / "_template" / "writeup-template.html"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0 Safari/537.36"
)

CATEGORY_PATTERNS = [
    (re.compile(r"\btryhackme\b|\bthm\b", re.I), "thm-writeups"),
    (re.compile(r"\bhackthebox\b|\bhtb\b", re.I), "htb-writeups"),
    (re.compile(r"\bwebverse\b", re.I), "webverse-writeups"),
    (re.compile(r"\bbugforge\b", re.I), "bugforge-writeups"),
    (re.compile(r"\bvulnhub\b", re.I), "vulnhub-writeups"),
]

DEST_TO_ACTIVE_HREF = {
    "htb-writeups": "../hackthebox.html",
    "thm-writeups": "../tryhackme.html",
    "vulnhub-writeups": "../vulnhub.html",
    "bugforge-writeups": "../bugforge.html",
    "webverse-writeups": "../webverse.html",
}


# ---------- filename + title helpers ----------

def slugify_filename(filename: str) -> str:
    """Convert a Medium export filename to a clean slug.

    Example:
        '2025-12-27_MD2PDF---Writeup--TryHackMe--1f9342e0b042.html'
        -> 'md2pdf-writeup-tryhackme'
    """
    name = Path(filename).stem
    name = re.sub(r"^\d{4}-\d{2}-\d{2}_", "", name)
    name = re.sub(r"-[0-9a-f]{12,}$", "", name)
    name = re.sub(r"-+", "-", name)
    name = name.lower().strip("-")
    return name or "untitled"


def date_from_filename(filename: str) -> str:
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", Path(filename).stem)
    return m.group(1) if m else ""


def suggest_category(title: str, filename: str, body_text: str = "") -> str:
    """Try filename + title first; if nothing matches, fall back to body text."""
    haystack = f"{title or ''}  {filename}"
    for pattern, dest in CATEGORY_PATTERNS:
        if pattern.search(haystack):
            return dest
    # filename gave nothing — scan the body
    if body_text:
        for pattern, dest in CATEGORY_PATTERNS:
            if pattern.search(body_text):
                return dest
    return ""


# ---------- parsing ----------

def parse_medium_export(filepath: Path) -> dict:
    """Pull title, body, canonical URL and date out of a Medium export file."""
    html = filepath.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")

    title_el = soup.find(class_="p-name")
    title = title_el.get_text(strip=True) if title_el else filepath.stem

    canonical_el = soup.find(class_="p-canonical")
    canonical = canonical_el.get("href") if canonical_el else ""

    time_el = soup.find("time", class_="dt-published")
    date = (time_el.get("datetime", "") or "")[:10] if time_el else ""

    body = soup.find("section", attrs={"data-field": "body"})

    return {
        "title": title,
        "body": body,
        "canonical": canonical,
        "date": date,
    }


# ---------- 'init' subcommand ----------

def cmd_init(args) -> None:
    posts_dir = Path(args.posts) if args.posts else POSTS_DIR
    manifest_path = Path(args.manifest) if args.manifest else MANIFEST

    if not posts_dir.exists():
        sys.exit(f"posts dir not found: {posts_dir}")

    rows = []
    for html_path in sorted(posts_dir.glob("*.html")):
        try:
            info = parse_medium_export(html_path)
        except Exception as e:
            print(f"  failed to parse {html_path.name}: {e}", file=sys.stderr)
            continue
        slug = slugify_filename(html_path.name)
        body_text = info["body"].get_text(" ", strip=True)[:3000] if info["body"] else ""
        suggested = suggest_category(info["title"], html_path.name, body_text)
        rows.append({
            "filename": html_path.name,
            "slug": slug,
            "title": info["title"],
            "date": info["date"] or date_from_filename(html_path.name),
            "suggested_dest": suggested,
            "dest": suggested,
        })

    # Disambiguate duplicate slugs by appending the short Medium post hash
    slug_counts: dict = {}
    for r in rows:
        slug_counts[r["slug"]] = slug_counts.get(r["slug"], 0) + 1
    for r in rows:
        if slug_counts[r["slug"]] > 1:
            m = re.search(r"-([0-9a-f]{12})\.html$", r["filename"])
            if m:
                r["slug"] = f"{r['slug']}-{m.group(1)[:8]}"

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["filename", "slug", "title", "date", "suggested_dest", "dest"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    print(f"Wrote {len(rows)} rows to {manifest_path}")
    by_dest: dict = {}
    for r in rows:
        key = r["suggested_dest"] or "(unknown - probably a comment)"
        by_dest[key] = by_dest.get(key, 0) + 1
    print()
    for k, v in sorted(by_dest.items()):
        print(f"  {k}: {v}")
    print()
    print(f"Next step: open {manifest_path} and:")
    print("  - blank the 'dest' column for any rows you don't want imported")
    print("  - fix 'dest' for any rows the auto-suggest got wrong")
    print()
    print("Then run:  python3 _scripts/import-medium.py import")


# ---------- image download ----------

def download_image(url: str, dest_path: Path, delay: float = 0.2) -> str:
    if dest_path.exists() and dest_path.stat().st_size > 0:
        return "cached"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_bytes(data)
    time.sleep(delay)
    return "downloaded"


# ---------- body cleanup ----------

KEEP_ATTRS_DEFAULT = {"src", "href", "alt"}


def clean_body(body_soup, slug: str, image_dir: Path, delay: float) -> str:
    """Download images, strip Medium classes, return inner HTML string."""
    if body_soup is None:
        return ""

    # --- download images and rewrite src ---
    for img in body_soup.find_all("img"):
        src = img.get("src") or img.get("data-src")
        if not src or not src.startswith("http"):
            continue

        image_id = img.get("data-image-id")
        if image_id:
            filename = image_id
        else:
            filename = Path(urllib.parse.urlparse(src).path).name or "image.png"

        local_path = image_dir / filename
        try:
            status = download_image(src, local_path, delay=delay)
            print(f"    [img] {filename} ({status})")
        except Exception as e:
            print(f"    [img] FAILED {src[:70]}: {e}", file=sys.stderr)
            continue

        img["src"] = f"images/{slug}/{filename}"

        # use figure's figcaption text as alt if no alt set
        figure = img.find_parent("figure")
        if figure:
            cap = figure.find("figcaption")
            if cap and cap.get_text(strip=True):
                img["alt"] = cap.get_text(strip=True)

        for attr in list(img.attrs.keys()):
            if attr not in ("src", "alt"):
                del img.attrs[attr]

    # --- normalise YouTube iframes ---
    # Medium gives src="https://www.youtube.com/embed/VIDEOID?feature=oembed".
    # The ?feature=oembed parameter and the youtube.com origin combine to
    # produce "Error 153 - Video player configuration error" when loaded
    # outside Medium (e.g. file:// or this site). Swap to youtube-nocookie.com
    # and drop the oembed parameter - that domain is more permissive about
    # embed origins.
    for iframe in body_soup.find_all("iframe"):
        src = iframe.get("src") or ""
        if "youtube.com/embed/" in src:
            src = src.replace("youtube.com/embed/", "youtube-nocookie.com/embed/")
            src = re.sub(r"\?feature=oembed", "", src)
            iframe["src"] = src

    # --- strip / convert tags ---
    for el in list(body_soup.find_all(True)):
        if not isinstance(el, Tag):
            continue

        if el.name == "pre":
            # convert Medium's syntax-highlighted code block to our themed one
            for span in el.find_all("span"):
                span.unwrap()
            for br in el.find_all("br"):
                br.replace_with("\n")
            el.attrs = {"class": "code-view-two"}
        elif el.name == "figure":
            el.attrs = {}
        elif el.name == "figcaption":
            el.attrs = {"class": "imageCaption"}
        elif el.name in ("div", "section"):
            # unwrap Medium's div soup so we don't carry their layout structure
            el.unwrap()
        else:
            el.attrs = {k: v for k, v in el.attrs.items() if k in KEEP_ATTRS_DEFAULT}

    # drop the leading duplicate title (Medium puts an <h3 class="graf--title">)
    first_h3 = body_soup.find("h3")
    if first_h3:
        first_h3.decompose()

    # drop the boilerplate "buy me a coffee" / "quick message" paragraph
    for p in body_soup.find_all("p"):
        text = (p.get_text() or "").lower()
        if "buymeacoffee" in text or "quick message to readers" in text:
            p.decompose()

    # demote any remaining h3 -> h2 so they match our writeup heading style
    for h3 in body_soup.find_all("h3"):
        h3.name = "h2"

    if body_soup.name == "section":
        return "".join(str(c) for c in body_soup.children)
    return str(body_soup)


# ---------- import one post ----------

def import_one(row: dict, force: bool, delay: float) -> str:
    filename = row["filename"]
    slug = row["slug"]
    title = row["title"]
    dest = row["dest"].strip()

    if not dest:
        return "skipped"

    src_path = POSTS_DIR / filename
    if not src_path.exists():
        print(f"    source not found: {src_path}", file=sys.stderr)
        return "error"

    out_path = ROOT / dest / f"{slug}.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if out_path.exists() and not force:
        return "exists"

    info = parse_medium_export(src_path)
    # Tidy the displayed title: collapse multiple spaces and stray dashes
    info["title"] = re.sub(r"\s+", " ", info["title"]).strip()
    info["title"] = re.sub(r"\s*-\s*", " - ", info["title"])
    info["title"] = re.sub(r" -\s*Writeup", " Writeup", info["title"], flags=re.I)

    image_dir = out_path.parent / "images" / slug
    body_html = clean_body(info["body"], slug, image_dir, delay=delay)

    template = TEMPLATE.read_text(encoding="utf-8")

    # strip the HOW TO USE comment, leave a small attribution line instead
    template = re.sub(
        r"<!--\s*=+\s*WRITEUP TEMPLATE.*?=+\s*-->\s*",
        f"<!-- Imported from Medium: {info['canonical']} -->\n\n    ",
        template,
        count=1,
        flags=re.DOTALL,
    )

    # remove the "EDIT: add class='active'" hint
    template = re.sub(r"\s*<!--\s*EDIT:\s*add class=\"active\"[^>]*-->", "", template)

    # mark the right category active in the writeups dropdown
    active_href = DEST_TO_ACTIVE_HREF.get(dest)
    if active_href:
        template = template.replace(
            f'<a href="{active_href}">',
            f'<a class="active" href="{active_href}">',
            1,
        )

    # drop the placeholder hero image div - imported posts have their own first image
    template = re.sub(
        r"<!--\s*===== Hero / header image.*?-->\s*<div id=\"center-writeup-image\">.*?</div>\s*",
        "",
        template,
        count=1,
        flags=re.DOTALL,
    )

    # MACHINE_NAME -> real title
    title = info["title"]
    safe_title = (
        title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )
    # Avoid "Foo Writeup Writeup" if title already ends with "Writeup"
    if re.search(r"writeup\s*$", title, re.I):
        template = template.replace(
            "<title>MACHINE_NAME Writeup // 7s26simon</title>",
            f"<title>{safe_title} // 7s26simon</title>",
            1,
        )
        template = template.replace("MACHINE_NAME Writeup", safe_title)
    template = template.replace("MACHINE_NAME", safe_title)

    # swap out the marg-asthetic body with the cleaned content
    # (template ends marg-asthetic with </div> right before <section id="social-media">)
    new_body_block = (
        '<div id="marg-asthetic">\n'
        + body_html
        + '\n    </div>'
    )
    template, n = re.subn(
        r"<!-- ===== Main writeup body.*?-->\s*<div id=\"marg-asthetic\">.*?</div>(?=\s*<section id=\"social-media\")",
        new_body_block,
        template,
        count=1,
        flags=re.DOTALL,
    )
    if n == 0:
        # Fallback: match without the leading comment in case it's been stripped
        template, n = re.subn(
            r"<div id=\"marg-asthetic\">.*?</div>(?=\s*<section id=\"social-media\")",
            new_body_block,
            template,
            count=1,
            flags=re.DOTALL,
        )
    if n == 0:
        print(f"    WARN: body-swap regex did not match - placeholder content may remain", file=sys.stderr)

    out_path.write_text(template, encoding="utf-8")
    return "imported"


# ---------- 'import' subcommand ----------

def cmd_import(args) -> None:
    manifest_path = Path(args.manifest) if args.manifest else MANIFEST
    if not manifest_path.exists():
        sys.exit(f"manifest not found: {manifest_path}\nRun 'init' first.")

    with manifest_path.open("r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        sys.exit("manifest is empty")

    total = len(rows)
    counts = {"imported": 0, "skipped": 0, "exists": 0, "error": 0}

    for i, row in enumerate(rows, 1):
        title = (row.get("title") or "")[:70]
        dest = (row.get("dest") or "").strip()

        if not dest:
            print(f"[{i:>3}/{total}] {title} -- skipped (no dest)")
            counts["skipped"] += 1
            continue

        print(f"[{i:>3}/{total}] {title}")
        print(f"          -> {dest}/{row['slug']}.html")
        try:
            result = import_one(row, force=args.force, delay=args.delay)
        except Exception as e:
            print(f"          ERROR: {e}", file=sys.stderr)
            counts["error"] += 1
            continue
        counts[result] = counts.get(result, 0) + 1
        if result == "exists":
            print(f"          (skipped - exists, use --force to overwrite)")

    print()
    print("Summary:")
    for k, v in counts.items():
        if v:
            print(f"  {k:>10}: {v}")


# ---------- entry point ----------

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("init", help="Generate manifest.csv from posts/")
    pi.add_argument("--posts", help="Posts dir (default: ./posts)")
    pi.add_argument("--manifest", help="Output path (default: _scripts/manifest.csv)")

    pm = sub.add_parser("import", help="Read manifest.csv and import posts")
    pm.add_argument("--manifest", help="Manifest path (default: _scripts/manifest.csv)")
    pm.add_argument("--force", action="store_true", help="Overwrite existing output files")
    pm.add_argument("--delay", type=float, default=0.2, help="Seconds between image downloads (default: 0.2)")

    args = p.parse_args()
    if args.cmd == "init":
        cmd_init(args)
    elif args.cmd == "import":
        cmd_import(args)


if __name__ == "__main__":
    main()
