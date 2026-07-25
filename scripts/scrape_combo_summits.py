#!/usr/bin/env python3
"""
Rebuild data/combo_summits.csv by scraping 14ers.com.

14ers.com groups peaks by trailhead/area and lists every route in the
group on every peak in it. For single-peak routes the CSV's
is_primary_for_peak flag sorts that out, but combo routes are never
primary for anything, and area grouping puts 5 of the 11 on peaks they
never touch (Bells Traverse on Pyramid, Crestones Traverse on Humboldt,
Little Bear + Blanca on Ellingwood, Blanca and Ellingwood on Little
Bear, Mt. Wilson + El Diente on Wilson Peak).

Each route page carries a "Summit(s)" stat block listing one link per
summit, which is the authoritative list. build_data.py uses the output
to decide which peaks a combo belongs on.

Usage:
  python3 scripts/scrape_combo_summits.py

Polite by default: one request per combo, 0.4s apart, ~11 requests.
"""
import argparse
import csv
import os
import re
import sys
import time
import urllib.request

UA = {"User-Agent": "Mozilla/5.0"}

# The Summit(s) block holds one <a href="/peaks/ID/slug"> per summit.
# The ID in those hrefs is NOT reliable -- combo pages reuse a single
# peak id across every link -- so match on the slug, which is unique.
SUMMIT_BLOCK = re.compile(
    r'class="label">Summit\(s\)</span><span class="value">(.*?)</span></div>', re.S)
PEAK_SLUG = re.compile(r'href="/peaks/\d+/([a-z0-9-]+)"')


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")


def combo_keys(routes_csv: str):
    """route_key -> route_name for every row flagged COMBO."""
    with open(routes_csv) as f:
        rows = [r for r in csv.DictReader(f)
                if r["difficulty"] not in ("false", "true", "")]
    out = {}
    for r in rows:
        if r["route_summits"] == "COMBO":
            out.setdefault(r["route_key"], r["route_name"])
    return dict(sorted(out.items()))


def scrape(routes_csv: str, out_csv: str, delay: float) -> int:
    combos = combo_keys(routes_csv)
    if not combos:
        print("no COMBO rows found in routes csv", file=sys.stderr)
        return 1
    print(f"{len(combos)} combo routes to scrape")

    results, failed = {}, []
    for key, name in combos.items():
        try:
            block = SUMMIT_BLOCK.search(fetch(
                f"https://www.14ers.com/route.php?route={key}"))
            slugs = list(dict.fromkeys(PEAK_SLUG.findall(block.group(1)))) if block else []
        except Exception as exc:                      # network / parse
            slugs = []
            failed.append(f"{key}: {exc}")
        if not slugs:
            failed.append(f"{key}: no Summit(s) links found")
        results[key] = slugs
        print(f"  {key:8} {name[:40]:42} {slugs}")
        time.sleep(delay)

    if failed:
        print("\n".join(["failed:"] + [f"  {f}" for f in failed]), file=sys.stderr)
        print("refusing to write a partial file", file=sys.stderr)
        return 1

    # data/ csvs are kept read-only; loosen just long enough to rewrite.
    if os.path.exists(out_csv):
        os.chmod(out_csv, 0o600)
    with open(out_csv, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["route_key", "route_name", "summit_slugs"])
        for key, slugs in results.items():
            w.writerow([key, combos[key], " ".join(slugs)])
    os.chmod(out_csv, 0o400)
    print(f"\nwrote {out_csv}: {len(results)} combos")
    print("next: run scripts/build_data.py, then scripts/embed_data.py")
    return 0


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(here)
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--routes",
                    default=os.path.join(repo, "data", "colorado_14ers_routes.csv"))
    ap.add_argument("--out",
                    default=os.path.join(repo, "data", "combo_summits.csv"))
    ap.add_argument("--delay", type=float, default=0.4,
                    help="seconds between requests (default: 0.4)")
    args = ap.parse_args()

    if not os.path.exists(args.routes):
        print(f"missing routes csv: {args.routes}", file=sys.stderr)
        return 1
    return scrape(args.routes, args.out, args.delay)


if __name__ == "__main__":
    sys.exit(main())
