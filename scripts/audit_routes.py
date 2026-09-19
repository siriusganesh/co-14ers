#!/usr/bin/env python3
"""
Diff data/colorado_14ers_routes.csv against the live 14ers.com route pages.

The CSV was scraped from routeselector.php, which now returns 404. There is no
bulk source left, so the per-route pages are the only remaining authority and
the only way to check the file is one request per route. This fetches each
page once, caches the HTML under .cache/routes/, and reports every field that
disagrees. Re-runs read the cache and cost nothing; --refetch drops it.

Usage:
  python3 scripts/audit_routes.py              # fetch what is missing, diff
  python3 scripts/audit_routes.py --no-fetch   # diff from the cache only
  python3 scripts/audit_routes.py --refetch    # ignore the cache

Checked: YDS class, elevation gain, round-trip distance, trailhead road
rating, and the four risk ratings.

Three disagreements the diff deliberately tolerates, because reporting them
buries the real ones:

  * A snow grade. Our CSV concatenates it ("Class 2 Easy Snow"); the page's
    structured YDS field does not. The class compare strips it. Without that,
    32 snow routes report as wrong and not one of them is.

  * A gain or distance published per starting point ("From 4WD TH: 4,200
    feet"). Our value agrees when it appears anywhere in that list, since
    picking a different trailhead is a choice, not an error. Only a value
    published nowhere on the page is reported.

  * Numbers written without a unit ("From TH: 15"). Every number on the line
    is collected, not only the ones a unit anchors, so a bare figure still
    counts as published. The cost is over-collection: "starting near 11,000"
    contributes 11000, which could mask a real gain error. That direction is
    the safe one. This audit is built to under-report rather than hand back
    false positives.

Exit status is 1 when any field disagrees, so CI can gate on it.
"""
import argparse
import csv
import os
import re
import sys
import time
import urllib.request
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ROUTES_CSV = os.path.join(ROOT, "data", "colorado_14ers_routes.csv")
CACHE = os.path.join(ROOT, ".cache", "routes")
URL = "https://www.14ers.com/route.php?route=%s"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36")

RISK_FIELDS = [("exposure", "Exposure"), ("rockfall", "Rockfall"),
               ("route_finding", "Route-Finding"), ("commitment", "Commitment")]
SNOW = re.compile(r"\s+(Easy|Moderate|Steep|Difficult)\s+Snow\s*$", re.I)
PROP = re.compile(r'"name":\s*"([^"]+)",\s*"value":\s*"([^"]*)"')
# A number, unless it is the drive rating in "4WD" / "2WD" or the digit in a
# name like "C2 Couloir".
NUMBER = re.compile(r"(?<![A-Za-z])([\d,]*\.?\d+)(?!\s*WD)")


def norm(s):
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def base_class(s):
    """Class without the trailing snow grade, which lives in its own field
    on the page and is concatenated into ours."""
    return norm(SNOW.sub("", str(s or "")))


def numbers(s):
    """Every number on the line, as floats. Over-collects on purpose; see the
    module docstring."""
    out = set()
    for m in NUMBER.finditer(str(s or "")):
        try:
            out.add(float(m.group(1).replace(",", "")))
        except ValueError:
            pass
    return out


def first_number(s):
    for v in NUMBER.finditer(str(s or "")):
        try:
            return float(v.group(1).replace(",", ""))
        except ValueError:
            return None
    return None


def stat_block(html, label):
    """The visible stat row for a label, tags stripped. The JSON-LD copy of
    gain and distance is unusable for parsing: it runs the variants together
    with no separator."""
    m = re.search(r'<div class="stat">(?:(?!</div>).)*?>' + label +
                  r'</span>(.*?)</div>', html, re.S)
    if not m:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(1))).strip()


def rating(html, label):
    m = re.search(r">" + label + r"</span><span[^>]*>([^<]+)</span>", html)
    return m.group(1).strip() if m else None


def fetch(key, mode):
    """Cached page text, or None. mode: 'auto', 'never' or 'always'."""
    path = os.path.join(CACHE, key + ".html")
    if mode != "always" and os.path.exists(path) and os.path.getsize(path) > 5000:
        return open(path, encoding="utf-8", errors="replace").read()
    if mode == "never":
        return None
    os.makedirs(CACHE, exist_ok=True)
    for attempt in (1, 2):
        try:
            req = urllib.request.Request(URL % key, headers={"User-Agent": UA})
            html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
            open(path, "w", encoding="utf-8").write(html)
            time.sleep(1.0)          # one request a second, their server
            return html
        except Exception as exc:
            if attempt == 2:
                print("  fetch failed %s: %s" % (key, exc), file=sys.stderr)
                return None
            time.sleep(3)


def csv_routes(path):
    """One row per route_key. 14ers.com groups peaks by area, so the CSV
    repeats a route on every peak in its group; the duplicates are checked
    against each other and then collapsed."""
    rows = [r for r in csv.DictReader(open(path))
            if r["difficulty"] not in ("false", "true", "")]
    fields = ["difficulty", "elevation_gain", "distance", "exposure", "rockfall",
              "route_finding", "commitment", "road_difficulty"]
    out, disagree = {}, set()
    for r in rows:
        k = r["route_key"]
        if k not in out:
            out[k] = r
        elif any(norm(out[k][f]) != norm(r[f]) for f in fields):
            disagree.add(k)
    return out, disagree


def audit(fetch_mode):
    ours, disagree = csv_routes(ROUTES_CSV)
    print("routes in CSV: %d" % len(ours))
    if disagree:
        print("duplicate rows that disagree with each other: %s" % " ".join(sorted(disagree)))

    found = defaultdict(list)
    missing = []
    for key in sorted(ours):
        html = fetch(key, fetch_mode)
        if not html:
            missing.append(key)
            continue
        row = ours[key]
        name = row["route_name"][:38]

        props = {}
        for m in PROP.finditer(html):
            props.setdefault(m.group(1), m.group(2))

        live_class = props.get("YDS Class")
        if live_class and base_class(row["difficulty"]) != base_class(live_class):
            found["class"].append((key, name, row["difficulty"], live_class))

        for col, label in (("elevation_gain", "Elevation Gain"),
                           ("distance", "Round-Trip")):
            raw = stat_block(html, label) or (stat_block(html, "Length")
                                              if col == "distance" else "")
            published = numbers(raw)
            mine = first_number(row[col])
            if published and mine is not None and mine not in published:
                found[col].append((key, name, row[col],
                                   " / ".join("%g" % v for v in sorted(published))))

        live_road = first_number(props.get("Trailhead Accessibility"))
        if row.get("road_difficulty") not in (None, "") and live_road is not None:
            if float(row["road_difficulty"]) != live_road:
                found["road"].append((key, name, row["road_difficulty"], "%g" % live_road))

        for col, label in RISK_FIELDS:
            live = rating(html, label)
            if live and norm(row[col]) != norm(live):
                found[col].append((key, name, row[col], live))

    if missing:
        print("no page for: %s" % " ".join(missing))
    total = sum(len(v) for v in found.values())
    for field in ["class", "road"] + [c for c, _ in RISK_FIELDS] + \
                 ["elevation_gain", "distance"]:
        hits = found.get(field) or []
        print("\n== %s: %d" % (field, len(hits)))
        for key, name, mine, live in hits:
            print("   %-8s %-38s ours %-12s page %s" % (key, name, mine, live))
    print("\n%d field(s) disagree across %d route(s)"
          % (total, len({h[0] for v in found.values() for h in v})))
    return total


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--no-fetch", action="store_true",
                    help="diff from the cache only, make no requests")
    ap.add_argument("--refetch", action="store_true",
                    help="ignore the cache and fetch every page again")
    args = ap.parse_args()
    mode = "never" if args.no_fetch else ("always" if args.refetch else "auto")
    sys.exit(1 if audit(mode) else 0)


if __name__ == "__main__":
    main()
