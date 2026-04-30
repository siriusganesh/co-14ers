#!/usr/bin/env python3
"""
Replace the inlined `const PEAKS = [...]` literal in index.html with the
contents of peaks.json. Run after build_data.py to push fresh data into
the live site.

Usage: python3 scripts/embed_data.py
"""
import json
import os
import re
import sys


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(here)
    json_path = os.path.join(repo, "peaks.json")
    html_path = os.path.join(repo, "index.html")

    with open(json_path) as f:
        peaks_min = json.dumps(json.load(f), separators=(",", ":"))

    with open(html_path) as f:
        html = f.read()

    pattern = re.compile(r"const PEAKS = \[.*?\];", re.DOTALL)
    if not pattern.search(html):
        print("could not find `const PEAKS = [...];` in index.html", file=sys.stderr)
        return 1

    new_html, n = pattern.subn(f"const PEAKS = {peaks_min};", html, count=1)
    if n != 1:
        print(f"expected 1 substitution, made {n}", file=sys.stderr)
        return 1

    with open(html_path, "w") as f:
        f.write(new_html)

    print(f"updated {html_path} with peaks.json ({len(peaks_min):,} bytes inlined)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
