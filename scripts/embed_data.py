#!/usr/bin/env python3
"""
Push the two generated regions of index.html back into sync with their
sources, so the page still loads in one request:

  * `const PEAKS = [...]` from peaks.json. Run after build_data.py.
  * the SEARCH MODULE block from search.mjs, minus its trailing export
    block, which only Node needs.

Usage: python3 scripts/embed_data.py
       python3 scripts/embed_data.py --check   # verify, change nothing

--check exits non-zero when index.html disagrees with either source. That is
what CI runs, to catch an edit made to the inlined copy instead of to
search.mjs.
"""
import json
import os
import re
import sys

BEGIN = "// ==== SEARCH MODULE (inlined from search.mjs by scripts/embed_data.py) ====\n"
END = "// ==== END SEARCH MODULE ====\n"


def peaks_literal(repo: str) -> str:
    with open(os.path.join(repo, "peaks.json")) as f:
        return "const PEAKS = %s;" % json.dumps(json.load(f), separators=(",", ":"))


def search_body(repo: str) -> str:
    """search.mjs with its export block dropped.

    That block is the one thing the browser cannot have and Node cannot do
    without, so it is the only difference between the two copies. Keeping it
    to a single trailing statement makes the inlining a truncation rather
    than a transform, which is what lets --check compare the rest byte for
    byte.
    """
    with open(os.path.join(repo, "search.mjs")) as f:
        mod = f.read()
    at = mod.find("\nexport {")
    if at < 0:
        raise SystemExit("search.mjs has no trailing `export {` block")
    return mod[:at].rstrip() + "\n"


def replace_peaks(html: str, literal: str) -> str:
    pattern = re.compile(r"const PEAKS = \[.*?\];", re.DOTALL)
    if not pattern.search(html):
        raise SystemExit("could not find `const PEAKS = [...];` in index.html")
    new_html, n = pattern.subn(lambda _: literal, html, count=1)
    if n != 1:
        raise SystemExit("expected 1 PEAKS substitution, made %d" % n)
    return new_html


def replace_search(html: str, body: str) -> str:
    i = html.find(BEGIN)
    j = html.find(END, i + 1) if i >= 0 else -1
    if i < 0 or j < 0:
        raise SystemExit("could not find the SEARCH MODULE markers in index.html")
    return html[: i + len(BEGIN)] + body + html[j:]


def main(argv) -> int:
    check = "--check" in argv[1:]
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(here)
    html_path = os.path.join(repo, "index.html")

    with open(html_path) as f:
        html = f.read()

    literal = peaks_literal(repo)
    body = search_body(repo)
    new_html = replace_search(replace_peaks(html, literal), body)

    if check:
        if new_html == html:
            print("index.html is in sync with peaks.json and search.mjs")
            return 0
        stale = []
        if replace_peaks(html, literal) != html:
            stale.append("peaks.json")
        if replace_search(html, body) != html:
            stale.append("search.mjs")
        print(
            "index.html is out of sync with %s.\n"
            "Run `python3 scripts/embed_data.py` and commit the result. If you "
            "edited the inlined copy inside index.html, move that edit to the "
            "source file instead: the inlined copy is generated."
            % " and ".join(stale),
            file=sys.stderr,
        )
        return 1

    if new_html == html:
        print("index.html already in sync; nothing to do")
        return 0

    with open(html_path, "w") as f:
        f.write(new_html)

    print(
        "updated %s (%s bytes of peaks.json, %s bytes of search.mjs inlined)"
        % (html_path, format(len(literal), ","), format(len(body), ","))
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
