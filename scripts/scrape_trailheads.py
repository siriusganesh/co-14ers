#!/usr/bin/env python3
"""
Refresh the trailhead columns in data/colorado_14ers_routes.csv.

Fills trailhead_name / trailhead_lat / trailhead_lon for every route, so
the detail panel can link each route to a Google Maps pin at its
trailhead. Two hops per route:

  route.php?route=KEY          -> the labeled "Trailhead" stat, which
                                  gives a thparm id and display name
  trailheadsview.php?thparm=ID -> the coordinates

Coordinates come from the page's startlat/startlon map parameters rather
than the human-readable "lat, lon" line. Both exist, but the readable
line varies in precision (Culebra, Yankee Boy Basin and Denny Creek
print 2-4 decimals where most print 5), which makes it easy to write a
regex that silently misses a handful. The map parameters are uniform.

Only the three trailhead columns are rewritten; every other field is
passed through untouched. Idempotent -- a clean re-run leaves the file
byte-identical, so `git diff` after running is the real check.

Usage:
  python3 scripts/scrape_trailheads.py            # rewrite in place
  python3 scripts/scrape_trailheads.py --dry-run  # report, change nothing

~156 route pages + ~70 trailhead pages, 0.4s apart: roughly 2 minutes.
"""
import argparse
import csv
import os
import re
import sys
import time
import urllib.request

UA = {"User-Agent": "Mozilla/5.0"}
BASE = "https://www.14ers.com"

# The route page's Trailhead stat. Anchored on the label because the nav
# and closure-alert blocks also link to trailheadsview.php and would
# otherwise match first.
TH_FIELD = re.compile(
    r'class="label">Trailhead</span>\s*<span class="value">\s*'
    r'<a href="[^"]*thparm=([a-z0-9]+)"[^>]*>([^<]+)</a>')
# Map start position, present on every trailhead page at full precision.
TH_COORDS = re.compile(r"startlat=(-?\d+\.?\d*)&startlon=(-?\d+\.?\d*)")

TH_COLUMNS = ["trailhead_name", "trailhead_lat", "trailhead_lon"]


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")


def scrape_route_trailheads(keys, delay: float, failed: list) -> dict:
    """route_key -> (thparm, display name)"""
    out = {}
    for n, key in enumerate(keys, 1):
        try:
            m = TH_FIELD.search(fetch(f"{BASE}/route.php?route={key}"))
            if m:
                out[key] = (m.group(1), m.group(2).strip())
            else:
                failed.append(f"route {key}: no Trailhead field")
        except Exception as exc:
            failed.append(f"route {key}: {exc}")
        time.sleep(delay)
        if n % 40 == 0:
            print(f"  {n}/{len(keys)} route pages", flush=True)
    return out


def scrape_coords(thparms, delay: float, failed: list) -> dict:
    """thparm -> (lat, lon)"""
    out = {}
    for n, th in enumerate(sorted(thparms), 1):
        try:
            m = TH_COORDS.search(fetch(f"{BASE}/php14ers/trailheadsview.php?thparm={th}"))
            if m:
                out[th] = (m.group(1), m.group(2))
            else:
                failed.append(f"trailhead {th}: no startlat/startlon")
        except Exception as exc:
            failed.append(f"trailhead {th}: {exc}")
        time.sleep(delay)
        if n % 25 == 0:
            print(f"  {n}/{len(thparms)} trailhead pages", flush=True)
    return out


def run(routes_csv: str, delay: float, dry_run: bool) -> int:
    with open(routes_csv) as f:
        rows = list(csv.DictReader(f))
    fields = list(rows[0].keys())
    missing = [c for c in TH_COLUMNS if c not in fields]
    if missing:
        print(f"routes csv lacks columns: {missing}", file=sys.stderr)
        return 1

    # Skip the header-ish junk rows the source scrape leaves behind.
    real = [r for r in rows if r["difficulty"] not in ("false", "true", "")]
    keys = sorted({r["route_key"] for r in real})
    print(f"{len(keys)} routes to resolve")

    failed = []
    route_th = scrape_route_trailheads(keys, delay, failed)
    thparms = {th for th, _ in route_th.values()}
    print(f"{len(thparms)} distinct trailheads")
    coords = scrape_coords(thparms, delay, failed)

    if failed:
        print("\n".join(["failed:"] + [f"  {f}" for f in failed]), file=sys.stderr)
        print("refusing to write a partial file", file=sys.stderr)
        return 1

    changes = []
    for r in real:
        th, name = route_th[r["route_key"]]
        lat, lon = coords[th]
        for col, val in zip(TH_COLUMNS, (name, lat, lon)):
            if r[col] != val:
                changes.append(f"  {r['route_key']:9} {r['peak_name'][:22]:24} "
                               f"{col}: {r[col]!r} -> {val!r}")
            r[col] = val

    print(f"\n{len(changes)} field(s) differ from the current file")
    print("\n".join(changes[:40]))
    if len(changes) > 40:
        print(f"  ... and {len(changes) - 40} more")

    if dry_run:
        print("dry run: nothing written")
        return 0

    # data/ csvs are kept read-only; loosen just long enough to rewrite.
    os.chmod(routes_csv, 0o600)
    with open(routes_csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    os.chmod(routes_csv, 0o400)
    print(f"wrote {routes_csv}")
    print("next: run scripts/build_data.py, then scripts/embed_data.py")
    return 0


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(here)
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--routes",
                    default=os.path.join(repo, "data", "colorado_14ers_routes.csv"))
    ap.add_argument("--delay", type=float, default=0.4,
                    help="seconds between requests (default: 0.4)")
    ap.add_argument("--dry-run", action="store_true",
                    help="report differences without writing")
    args = ap.parse_args()

    if not os.path.exists(args.routes):
        print(f"missing routes csv: {args.routes}", file=sys.stderr)
        return 1
    return run(args.routes, args.delay, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
