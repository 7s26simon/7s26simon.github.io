#!/usr/bin/env python3
"""
tag-vulns.py - Read each imported writeup, classify it by vulnerability
class(es) using title + body keyword analysis, and write a tagged CSV.

Produces _scripts/vuln-tags.csv with columns:
    slug, dest, title, date, categories

where 'categories' is a space-separated list of vuln tokens.

Run this after import-medium.py and populate-tables.py.
"""

import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "_scripts" / "manifest.csv"
OUT = ROOT / "_scripts" / "vuln-tags.csv"

# (token, regex pattern) - order matters: more specific first
# Each writeup gets all tokens whose pattern matches its title+body text.
VULN_PATTERNS = [
    # --- injection ---
    ("xss",                 r"\b(xss|rxss|sxss|cross[- ]site\s+scripting|reflected\s+xss|stored\s+xss|dom[- ]based\s+xss)\b|<script>.*alert\("),
    ("sqli",                r"\b(sqli|sql\s+injection|union\s+select|'\s*or\s+1\s*=\s*1|blind\s+sql)\b"),
    ("nosql",               r"\b(nosql\s+injection|mongo(db)?\s+injection)\b|\{\s*\"?\$ne\"?\s*:|\$gt\s*:|\$where\s*:"),
    ("graphql",             r"\b(graphql\s+(injection|vuln|abuse|introspection)|graphiql|__schema)\b|\bgraphql\b"),
    ("ssti",                r"\b(ssti|server[- ]side\s+template\s+injection|template\s+injection)\b|\{\{\s*7\s*\*\s*7|\{%.*%\}"),
    ("xxe",                 r"\b(xxe|xml\s+external\s+entity|xinclude)\b|<!ENTITY"),
    ("rce",                 r"\b(rce|remote\s+code\s+execution|command\s+injection|os\s+command\s+injection|code\s+execution|shell\s+injection)\b"),
    ("crlf",                r"\bcrlf\s+injection\b|%0d%0a"),
    ("ldap",                r"\bldap\s+injection\b"),

    # --- file / path ---
    ("lfi",                 r"\b(lfi|local\s+file\s+inclusion|rfi|remote\s+file\s+inclusion)\b"),
    ("path-traversal",      r"\b(path\s+traversal|directory\s+traversal)\b|\.\./\.\./"),
    ("upload",              r"\b(unrestricted\s+file\s+upload|arbitrary\s+file\s+upload|malicious\s+file\s+upload|webshell\s+upload)\b"),

    # --- auth / access ---
    ("weak-auth",           r"\b(weak\s+(creds|credentials|password)|default\s+(creds|credentials|password)|brute[- ]?forc(e|ing)|hydra)\b"),
    ("auth-bypass",         r"\b(auth(entication)?\s+bypass|login\s+bypass|password\s+bypass|broken\s+auth(entication)?)\b"),
    ("access-control",      r"\b(broken\s+access\s+control|missing\s+function\s+level|forced\s+browsing|privilege\s+escalation|priv[- ]?esc|bfla|broken\s+function\s+level|method[- ]based\s+access\s+control|bypass\s+paywall|paywall\s+bypass)\b|\bbac\b"),
    ("idor",                r"\b(idor|insecure\s+direct\s+object\s+references?)\b"),

    # --- session / token ---
    ("jwt",                 r"\b(jwt|json\s+web\s+token|jsonwebtoken)\b"),
    ("oauth",               r"\b(oauth(2|\s+misconfig)?|openid\s+connect)\b"),
    ("session",             r"\b(session\s+fixation|session\s+hijack|session\s+puzzle)\b"),

    # --- network / protocol ---
    ("ssrf",                r"\b(ssrf|server[- ]side\s+request\s+forgery)\b"),
    ("csrf",                r"\b(csrf|cross[- ]site\s+request\s+forgery)\b"),
    ("cors",                r"\b(cors\s+misconfig|cors\s+vulnerab|access[- ]control[- ]allow[- ]origin)\b"),
    ("smuggling",           r"\b(http\s+request\s+smuggling|request\s+smuggling|h2c\s+smuggling)\b"),
    ("redirect",            r"\bopen\s+redirect\b"),
    ("websocket",           r"\b(websockets?|ws://|wss://|websocket\s+(hijack|smuggl))\b"),

    # --- crypto / data ---
    ("deserialization",     r"\b(insecure\s+deserialization|unsafe\s+deserialization|deserialization\s+vuln|pickle\s+deserial|java\s+deserial)\b"),
    ("crypto",              r"\b(weak\s+(cryptography|encryption|hashing|cipher)|hash\s+collision|padding\s+oracle)\b"),
    ("prototype-pollution", r"\b(prototype\s+pollution|__proto__|constructor\.prototype)\b"),

    # --- logic / business ---
    ("business-logic",      r"\b(business\s+logic|workflow\s+(bypass|abuse)|logic\s+flaw|blf)\b"),
    ("race",                r"\b(race\s+condition|time[- ]?of[- ]?check)\b"),

    # --- misc ---
    ("stego",               r"\b(steganograph|steghide|exiftool\s+payload|hidden\s+(in|inside)\s+(the\s+)?image)\b"),
    ("info-disclosure",     r"\b(information\s+disclosure|sensitive\s+data\s+exposure|directory\s+listing|git\s+exposure|\.git\s+(folder|leak)|exposed\s+\.git)\b"),
    ("prompt-injection",    r"\b(prompt\s+injection|jailbreak|llm\s+injection|ai\s+jailbreak)\b"),
]


def extract_text(html: str) -> str:
    """Crude HTML-to-text - we only need keyword matching, not perfect prose."""
    # Strip script/style blocks
    html = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.I)
    html = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL | re.I)
    # Strip tags
    html = re.sub(r"<[^>]+>", " ", html)
    # Decode common entities
    html = html.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&nbsp;", " ").replace("&quot;", '"')
    # Collapse whitespace
    html = re.sub(r"\s+", " ", html)
    return html


def classify(text: str, title: str) -> list:
    """Return list of vuln tokens matching the writeup."""
    haystack = title + "  " + text
    hits = []
    for token, pattern in VULN_PATTERNS:
        if re.search(pattern, haystack, re.I):
            hits.append(token)

    # Heuristic post-processing:
    # - "priv-esc" / "BAC" in title are catch-alls; refine
    # - If "business-logic" matches, drop generic 'access-control' to keep tags tight
    # - If only 'rce' matched from a body that doesn't actually exploit RCE, leave it - it's overinclusive but the user can prune
    return hits


def main():
    if not MANIFEST.exists():
        raise SystemExit(f"manifest not found: {MANIFEST}")

    with MANIFEST.open() as f:
        rows = [r for r in csv.DictReader(f) if r["dest"].strip()]

    out_rows = []
    for r in rows:
        dest = r["dest"].strip()
        slug = r["slug"]
        title = r["title"]
        html_path = ROOT / dest / f"{slug}.html"
        if not html_path.exists():
            print(f"  missing: {html_path}")
            continue
        text = extract_text(html_path.read_text(encoding="utf-8"))
        tags = classify(text, title)
        if not tags:
            tags = []  # we'll surface these so the user can hand-tag
        out_rows.append({
            "slug": slug,
            "dest": dest,
            "title": title,
            "date": r["date"],
            "categories": " ".join(tags),
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["slug", "dest", "title", "date", "categories"])
        w.writeheader()
        w.writerows(out_rows)

    # Summary
    tagged = sum(1 for r in out_rows if r["categories"])
    untagged = sum(1 for r in out_rows if not r["categories"])
    print(f"Wrote {len(out_rows)} rows to {OUT}")
    print(f"  with tags:     {tagged}")
    print(f"  without tags:  {untagged}")
    print()

    from collections import Counter
    counter = Counter()
    for r in out_rows:
        for t in r["categories"].split():
            counter[t] += 1
    print("Tag frequency:")
    for tag, n in counter.most_common():
        print(f"  {n:>3}  {tag}")


if __name__ == "__main__":
    main()
