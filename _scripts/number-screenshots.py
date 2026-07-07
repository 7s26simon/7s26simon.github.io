#!/usr/bin/env python3
"""
number-screenshots.py - Rename screenshots in a folder to 1.png, 2.png, ...

Sorts oldest to newest by filename or by last-modified time, then renames
sequentially, keeping each file's original extension. A file whose name
matches the folder (e.g. snobble.png inside images/snobble/) is treated as
the hero image and left alone.

Usage:
  python3 _scripts/number-screenshots.py webverse-writeups/images/snobble
  python3 _scripts/number-screenshots.py <folder> --by name
  python3 _scripts/number-screenshots.py <folder> --dry-run

Options:
  --by {mtime,name}   Sort key (default: mtime)
  --dry-run           Show the renames without doing them
"""

import argparse
import sys
from pathlib import Path

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


def main():
    parser = argparse.ArgumentParser(description="Rename screenshots to 1.png, 2.png, ...")
    parser.add_argument("folder", type=Path, help="Folder containing the screenshots")
    parser.add_argument("--by", choices=["mtime", "name"], default="mtime",
                        help="Sort by last-modified time (default) or filename")
    parser.add_argument("--dry-run", action="store_true", help="Preview without renaming")
    args = parser.parse_args()

    folder = args.folder.resolve()
    if not folder.is_dir():
        print(f"Error: {args.folder} is not a directory.")
        sys.exit(1)

    files = [
        f for f in folder.iterdir()
        if f.is_file() and f.suffix.lower() in IMAGE_EXTS
        and f.stem != folder.name  # skip the hero image, e.g. snobble.png
    ]
    if not files:
        print("No images found.")
        sys.exit(0)

    key = (lambda f: f.stat().st_mtime) if args.by == "mtime" else (lambda f: f.name.lower())
    files.sort(key=key)

    plan = [(f, folder / f"{i}{f.suffix.lower()}") for i, f in enumerate(files, start=1)]

    for src, dst in plan:
        marker = "(no change)" if src == dst else ""
        print(f"  {src.name}  ->  {dst.name}  {marker}")

    if args.dry_run:
        print("\nDry run - nothing renamed.")
        return

    # Two-phase rename so existing 1.png/2.png names can't collide mid-way
    temps = []
    for src, dst in plan:
        if src == dst:
            temps.append((None, dst))
            continue
        tmp = src.with_name(f".renum-{dst.name}")
        src.rename(tmp)
        temps.append((tmp, dst))

    renamed = 0
    for tmp, dst in temps:
        if tmp is None:
            continue
        tmp.rename(dst)
        renamed += 1

    print(f"\nRenamed {renamed} file(s) in {folder}")


if __name__ == "__main__":
    main()
