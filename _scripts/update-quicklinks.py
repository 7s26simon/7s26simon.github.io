#!/usr/bin/env python3
"""
update-quicklinks.py - Take vuln-tags.csv (output of tag-vulns.py),
apply manual overrides for the writeups that didn't auto-tag,
and rewrite quicklinks.html with:
    - all 14 original curated entries (untouched)
    - 109 imported entries (tagged)
    - extended dropdown with all vuln tokens used
"""

import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TAGS_CSV = ROOT / "_scripts" / "vuln-tags.csv"
QUICKLINKS = ROOT / "quicklinks.html"

# Manual overrides for writeups the auto-tagger couldn't classify, derived
# from reading the body of each.
MANUAL_OVERRIDES = {
    "the-great-disappearing-act-tryhackme-writeup":           "access-control",
    "sokudo-writeup-bugforge-03f1384a":                       "auth-bypass weak-auth",
    "sokudo-writeup-bugforge-c9413182":                       "auth-bypass weak-auth",
    "sokudo-writeup-bugforge-0e2c54aa":                       "access-control",
    "ottergram-writeup-bugforge-1ecd388f":                    "idor",
    "cheesy-does-it-writeup-bugforge-70eca5f4":               "business-logic",
    "tanuki-writeup-bugforge-8bc0c8d4":                       "ssrf",
    "cafeclub-writeup-bugforge-c0e8f42b":                     "idor",
    "cheesy-does-it-walkthrough-bugforge":                    "business-logic",
    "tanuki-writeup-bugforge-a83b3d9f":                       "access-control",
    "copypasta-writeup-bugforge-74c34045":                    "auth-bypass weak-auth",
    "expressway-writeup-hackthebox":                          "weak-auth",
    "phone-vault-official-writeup-webverse":                  "xss",
    "brackish-brewing-co-with-verbtamper-v1-8-1-webverse":    "access-control",
    "disgruntled-employee-official-writeup-webverse-pro-com": "auth-bypass",
    "angry-teacher-official-walkthrough-webverse-pro-com":    "access-control",
    "reportverse-official-writeup-webverse-pro-com":          "ssrf",
    "bomb-threat-official-walkthrough-webverse-pro-com":      "access-control",
    "cafeclub-writeup-bugforge-aca44b33":                     "business-logic",
    "cafeclub-writeup-bugforge-afb70036":                     "weak-auth business-logic",
    "ottergram-writeup-bugforge":                             "idor",
    "sokudo-writeup-bugforge":                                "auth-bypass weak-auth",
    "tanuki-writeup-bugforge":                                "access-control",
    "cafeclub-writeup-bugforge":                              "idor",
    "copypasta-writeup-bugforge":                             "auth-bypass weak-auth",
    "cheesy-does-it-writeup-bugforge":                        "business-logic",
}

# Token -> friendly label for the dropdown
TOKEN_LABEL = {
    "auth-bypass":         "Auth Bypass",
    "access-control":      "Broken Access Control",
    "business-logic":      "Business Logic Flaw",
    "upload":              "File Upload",
    "graphql":             "GraphQL",
    "info-disclosure":     "Information Disclosure",
    "jwt":                 "JWT",
    "lfi":                 "LFI",
    "nosql":               "NoSQL",
    "path-traversal":      "Path Traversal",
    "prompt-injection":    "Prompt Injection",
    "race":                "Race Condition",
    "rce":                 "RCE",
    "sqli":                "SQL Injection",
    "ssrf":                "SSRF",
    "ssti":                "SSTI",
    "stego":               "Steganography",
    "weak-auth":           "Weak Creds",
    "websocket":           "WebSocket",
    "xss":                 "XSS",
    "xxe":                 "XXE",
    "idor":                "IDOR",
    "redirect":            "Open Redirect",
    "deserialization":     "Insecure Deserialization",
    "csrf":                "CSRF",
    "crypto":              "Weak Cryptography",
    "oauth":               "OAuth",
    "cors":                "CORS Misconfig",
    "session":             "Session",
    "smuggling":           "Request Smuggling",
    "crlf":                "CRLF Injection",
    "ldap":                "LDAP Injection",
    "prototype-pollution": "Prototype Pollution",
}

# Token -> display-text (for the row's vulnerability column) when rendering
TOKEN_DISPLAY = {
    "auth-bypass":         "Auth Bypass",
    "access-control":      "Broken Access Control",
    "business-logic":      "Business Logic",
    "upload":              "File Upload",
    "graphql":             "GraphQL",
    "info-disclosure":     "Info Disclosure",
    "jwt":                 "JWT",
    "lfi":                 "LFI",
    "nosql":               "NoSQL",
    "path-traversal":      "Path Traversal",
    "prompt-injection":    "Prompt Injection",
    "race":                "Race Condition",
    "rce":                 "RCE",
    "sqli":                "SQLi",
    "ssrf":                "SSRF",
    "ssti":                "SSTI",
    "stego":               "Steganography",
    "weak-auth":           "Weak Creds",
    "websocket":           "WebSocket",
    "xss":                 "XSS",
    "xxe":                 "XXE",
    "idor":                "IDOR",
    "redirect":            "Open Redirect",
    "deserialization":     "Deserialization",
    "csrf":                "CSRF",
    "crypto":              "Weak Crypto",
}

# Platform display names
DEST_TO_PLATFORM = {
    "htb-writeups":      "HackTheBox",
    "thm-writeups":      "TryHackMe",
    "vulnhub-writeups":  "Vulnhub",
    "bugforge-writeups": "BugForge",
    "webverse-writeups": "WebVerse",
}

# Original (pre-Medium) curated rows.
# (name, platform, dest_dir, slug, categories, display_text)
ORIGINAL_ROWS = [
    ("Legacy",                  "HackTheBox", "htb-writeups",     "legacy",       "rce",                                  "RCE"),
    ("Servmon",                 "HackTheBox", "htb-writeups",     "servmon",      "lfi path-traversal weak-auth",         "LFI, Path Traversal, Weak Creds"),
    ("Blunder",                 "HackTheBox", "htb-writeups",     "blunder",      "weak-auth upload rce",                 "Weak Creds, File Upload, RCE"),
    ("Tabby",                   "HackTheBox", "htb-writeups",     "tabby",        "lfi weak-auth access-control",         "LFI, Weak Creds, Broken Access Control"),
    ("Alfred",                  "TryHackMe",  "thm-writeups",     "alfred",       "weak-auth",                            "Weak Creds"),
    ("Ghostcat",                "TryHackMe",  "thm-writeups",     "ghostcat",     "lfi",                                  "LFI"),
    ("Jack",                    "TryHackMe",  "thm-writeups",     "jack",         "weak-auth access-control",             "Weak Creds, Broken Access Control"),
    ("Lian-Yu",                 "TryHackMe",  "thm-writeups",     "lianyu",       "stego access-control",                 "Steganography, Broken Access Control"),
    ("Year of The Rabbit",      "TryHackMe",  "thm-writeups",     "yotr",         "weak-auth auth-bypass",                "Weak Creds, Auth Bypass"),
    ("Dave's Blog",             "TryHackMe",  "thm-writeups",     "davesblog",    "nosql auth-bypass",                    "NoSQL, Auth Bypass"),
    ("Escalate my Privileges",  "Vulnhub",    "vulnhub-writeups", "emp-writeup",  "rce access-control",                   "RCE, Broken Access Control"),
    ("Geisha",                  "Vulnhub",    "vulnhub-writeups", "geisha",       "weak-auth access-control",             "Weak Creds, Broken Access Control"),
    ("Sumo",                    "Vulnhub",    "vulnhub-writeups", "sumo",         "rce",                                  "RCE"),
    ("Vegeta",                  "Vulnhub",    "vulnhub-writeups", "vegeta",       "stego access-control",                 "Steganography, Broken Access Control"),
]


def html_escape(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_display(tokens: list) -> str:
    """Convert a list of vuln tokens into the comma-separated display text."""
    labels = [TOKEN_DISPLAY.get(t, t) for t in tokens]
    # de-dupe while preserving order
    seen = set()
    out = []
    for l in labels:
        if l not in seen:
            seen.add(l)
            out.append(l)
    return ", ".join(out)


def main():
    with TAGS_CSV.open() as f:
        rows = list(csv.DictReader(f))

    # Apply manual overrides. Keys may reference pre-cleaning slugs that
    # still contained 'bugforge' / 'webverse' tokens, so we normalize both
    # sides with the same stripping rules and match against either form.
    SLUG_PLATFORM_TOKENS = ("bugforge-io", "bugforge", "webverse-pro-com", "webverse-pro", "webverse")

    def _normalize(slug: str) -> str:
        # preserve trailing 8-hex hash, strip platform tokens from the base
        m = re.match(r"^(.+)-([0-9a-f]{8})$", slug)
        if m:
            base, h = m.group(1), m.group(2)
            for tok in SLUG_PLATFORM_TOKENS:
                base = re.sub(rf"-{re.escape(tok)}$", "", base)
            return f"{base}-{h}"
        for tok in SLUG_PLATFORM_TOKENS:
            slug = re.sub(rf"-{re.escape(tok)}$", "", slug)
        return slug

    normalized_overrides = { _normalize(k): v for k, v in MANUAL_OVERRIDES.items() }

    for r in rows:
        key = _normalize(r["slug"])
        if key in normalized_overrides:
            r["categories"] = normalized_overrides[key]

    # Build the combined row list
    all_rows = []

    # original curated rows
    for name, platform, dest, slug, cats, disp in ORIGINAL_ROWS:
        all_rows.append({
            "name": name,
            "platform": platform,
            "categories": cats,
            "display": disp,
            "href": f"{dest}/{slug}.html",
            "date": "",  # originals aren't dated in this view; sort to bottom
        })

    # imported rows
    for r in rows:
        tokens = r["categories"].split()
        all_rows.append({
            "name": r["title"],
            "platform": DEST_TO_PLATFORM.get(r["dest"], r["dest"]),
            "categories": r["categories"],
            "display": format_display(tokens) if tokens else "(uncategorised)",
            "href": f"{r['dest']}/{r['slug']}.html",
            "date": r["date"],
        })

    # Sort: dated rows newest-first, then original undated rows after
    all_rows.sort(key=lambda r: (r["date"] == "", r["date"] or ""), reverse=True)
    # The above sorts undated to the end; we want originals at the bottom.
    # The boolean ("date" == "") will sort True (=1) AFTER False (=0)
    # when reverse=True we get True first. Fix by sorting in two passes:
    all_rows = (
        sorted([r for r in all_rows if r["date"]], key=lambda r: r["date"], reverse=True)
        + [r for r in all_rows if not r["date"]]
    )

    # Collect all tokens used across all rows
    used_tokens = set()
    for r in all_rows:
        for t in r["categories"].split():
            used_tokens.add(t)

    # Build dropdown options (sorted alphabetically by label, with "All" first)
    dropdown_items = []
    for token in used_tokens:
        label = TOKEN_LABEL.get(token, token)
        dropdown_items.append((label, token))
    dropdown_items.sort(key=lambda x: x[0].lower())

    dropdown_html = '                <option value="">All vulnerabilities</option>\n'
    dropdown_html += "\n".join(
        f'                <option value="{token}">{label}</option>'
        for label, token in dropdown_items
    )

    # Build the new <tbody>
    tbody_lines = []
    for r in all_rows:
        cats_attr = html_escape(r["categories"])
        tbody_lines.append(
            f'                <tr data-categories="{cats_attr}">'
            f'<td>{html_escape(r["name"])}</td>'
            f'<td>{html_escape(r["platform"])}</td>'
            f'<td>{html_escape(r["display"])}</td>'
            f'<td><a href="{r["href"]}">read</a></td>'
            f'</tr>'
        )
    tbody_html = "\n".join(tbody_lines)

    # Now patch quicklinks.html
    content = QUICKLINKS.read_text(encoding="utf-8")

    # Replace the <select> options
    content, n_select = re.subn(
        r"(<select id=\"cat-filter\">).*?(</select>)",
        lambda m: m.group(1) + "\n" + dropdown_html + "\n            " + m.group(2),
        content,
        count=1,
        flags=re.DOTALL,
    )
    if n_select == 0:
        raise SystemExit("could not find <select id=cat-filter> in quicklinks.html")

    # Replace the <tbody>
    new_tbody = "            <tbody>\n                <!--\n                Auto-generated by _scripts/update-quicklinks.py.\n                Edit data-categories on each row to fix tagging.\n                Tokens must match <option value=\"...\"> in the select above.\n                -->\n" + tbody_html + "\n            </tbody>"
    content, n_tbody = re.subn(
        r"<tbody>.*?</tbody>",
        new_tbody,
        content,
        count=1,
        flags=re.DOTALL,
    )
    if n_tbody == 0:
        raise SystemExit("could not find <tbody>...</tbody> in quicklinks.html")

    QUICKLINKS.write_text(content, encoding="utf-8")

    print(f"Wrote {len(all_rows)} rows to {QUICKLINKS}")
    print(f"  dropdown: {len(dropdown_items)} vulnerability categories")
    print(f"  used tokens: {' '.join(sorted(used_tokens))}")
    uncategorised = sum(1 for r in all_rows if r["display"] == "(uncategorised)")
    if uncategorised:
        print(f"  uncategorised: {uncategorised} rows (manual tagging needed)")


if __name__ == "__main__":
    main()
