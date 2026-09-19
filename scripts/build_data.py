#!/usr/bin/env python3
"""
Merge the two source CSVs into peaks.json.

Inputs (override with env vars or CLI args):
  data/colorado_14ers_peaks.csv
  data/colorado_14ers_routes.csv

Output:
  peaks.json  (consumed by index.html)

The CSVs are scraped from 14ers.com. To refresh data, drop new CSVs into data/
and re-run this script.
"""
import argparse
import csv
import json
import os
import re
import sys
from collections import defaultdict

# Composite difficulty score for a route, used to sort the Standard column.
#
# 14ers.com only publishes a coarse class (Class 1-4 with optional
# Easy/Difficult modifier), so 25 peaks share a bare "Class 2" standard
# route and tie when that column is sorted. This score keeps class
# dominant and orders peaks *within* a class bucket from two terms:
#
#   score = class + modifier_offset
#           + 0.08 * mean(normalized risk ratings)
#           + 0.12 * mean(normalized gain, normalized distance)
#   modifier_offset: Easy -0.3, none 0.0, Difficult +0.3
#
# The two spans still sum to 0.2, so the buckets never overlap (plain
# Class 2 spans 2.00-2.20, Difficult Class 2 spans 2.30-2.50, Easy
# Class 3 2.70-2.90, and so on) and no Class 3 peak can ever sort below
# a Class 2 one.
#
# The four risk factors are weighted equally and each is normalized
# against its own observed maximum, because the scales differ in
# practice: exposure, route-finding and commitment reach Extreme in
# this dataset while rockfall tops out at High. Gain and distance are
# normalized the same way, each against its own observed maximum.
#
# Gain and distance were excluded until Sept 2026. They came back after
# a reconciliation against 14ers.com routes_bydifficulty.php, which
# states it ranks on class, distance and gain. Class buckets already
# agreed for all 58 ranked routes and the route chosen per peak agreed
# too; only the within-bucket order differed, and gain and distance
# were the whole difference (inside plain Class 2 their order tracks
# gain x distance at rho 0.93, against 0.64 for a risk-only score).
# This 0.12/0.08 split fit their published order best: rho 0.994 over
# all 58 routes and a mean rank delta of 1.3 places, against 0.98 and
# 2.3 places for risk alone.
#
# This is still a derived, opinionated number -- not a 14ers.com
# rating. Counting effort has two known consequences: a long easy route
# now outranks a short hard one of the same class, which is the point;
# and a traverse row carries combined stats for several peaks, so a
# combo sorts high inside its own class bucket. The Standard column
# only ever reads single-peak routes, so the peak table is unaffected.
# 14ers.com groups peaks by trailhead/area and lists every route in the
# group on every peak in it, so the raw CSV attaches Little Bear's routes
# to Ellingwood Point and Eolus's to Windom. Three kinds of row survive
# that grouping; everything else is another peak's business:
#
#   route    - is_primary_for_peak, i.e. genuinely this peak's route.
#              Every one of the 138 is primary for exactly one peak.
#   combo    - a traverse or multi-peak day. Attachment is area-based and
#              wrong for 5 of the 11 (Bells Traverse lands on Pyramid,
#              Crestones Traverse on Humboldt), so these are matched
#              against the real Summit(s) list in data/combo_summits.csv.
#   approach - Chicago Basin, Lake Como and friends. Not summit routes,
#              but area grouping *is* the right semantics for an approach,
#              so the CSV's attachment is kept as-is.
KIND_ROUTE, KIND_COMBO, KIND_APPROACH = "route", "combo", "approach"
KIND_ORDER = {KIND_ROUTE: 0, KIND_COMBO: 1, KIND_APPROACH: 2}


def load_combo_summits(path: str) -> dict:
    """route_key -> set of peak slugs the combo actually summits."""
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return {row["route_key"]: row["summit_slugs"].split()
                for row in csv.DictReader(f)}


def summits_label(row, kind: str, combo_summits: dict, names_by_slug: dict):
    """The CSV stores the sentinels "COMBO" and "OTHER" in route_summits.
    Combos get the real peak list; approaches summit nothing."""
    if kind == KIND_COMBO:
        slugs = combo_summits.get(row["route_key"]) or []
        named = [names_by_slug[s] for s in slugs if s in names_by_slug]
        return ", ".join(named) or None
    if kind == KIND_APPROACH:
        return None
    return row["route_summits"]


def row_kind(row, combo_summits: dict):
    """Kind of row, or None if it belongs to a different peak."""
    if row["is_primary_for_peak"] == "true":
        return KIND_ROUTE
    if row["route_summits"] == "OTHER":
        return KIND_APPROACH
    if row["route_summits"] == "COMBO":
        summits = combo_summits.get(row["route_key"])
        # no scraped list yet: fall back to the CSV's attachment
        if summits is None or row["peak_slug"] in summits:
            return KIND_COMBO
        return None
    return None


RATING_VALUES = {"low": 0, "moderate": 1, "considerable": 2, "high": 3, "extreme": 4}
RISK_FACTORS = ["exposure", "rockfall", "route_finding", "commitment"]
RISK_SPAN = 0.08
EFFORT_SPAN = 0.12
MEASURE_RE = re.compile(r"[\d,.]+")


def class_number(difficulty: str):
    m = re.search(r"Class\s*(\d)", difficulty or "")
    return int(m.group(1)) if m else None


def modifier_offset(difficulty: str) -> float:
    """Leading Easy/Difficult only. "Class 2 Easy Snow" is a snow
    suffix, not an easy class, so it must not match here."""
    m = re.match(r"\s*(Easy|Difficult)\s+Class", difficulty or "")
    if not m:
        return 0.0
    return -0.3 if m.group(1).lower() == "easy" else 0.3


def rating_maxima(rows) -> dict:
    out = {}
    for f in RISK_FACTORS:
        vals = [RATING_VALUES[r[f].lower()] for r in rows
                if r.get(f) and r[f].lower() in RATING_VALUES]
        out[f] = max(vals) if vals else 1
    return out


def measure(value):
    """First number in a gain or distance cell. "4,500'" -> 4500.0,
    "9.75 mi" -> 9.75. None when the cell carries no number."""
    m = MEASURE_RE.search(str(value or ""))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", ""))
    except ValueError:
        return None


def effort_maxima(rows) -> dict:
    out = {}
    for name, col in (("gain", "elevation_gain"), ("distance", "distance")):
        vals = [v for v in (measure(r.get(col)) for r in rows) if v]
        out[name] = max(vals) if vals else 1.0
    return out


def difficulty_score(row, maxima: dict, effort: dict):
    n = class_number(row["difficulty"])
    if n is None:
        return None
    vals = [RATING_VALUES[row[f].lower()] / maxima[f] for f in RISK_FACTORS
            if row.get(f) and row[f].lower() in RATING_VALUES]
    risk = sum(vals) / len(vals) if vals else 0.0
    legs = [v / effort[name] for name, v in
            (("gain", measure(row.get("elevation_gain"))),
             ("distance", measure(row.get("distance")))) if v]
    work = sum(legs) / len(legs) if legs else 0.0
    return round(n + modifier_offset(row["difficulty"])
                 + RISK_SPAN * risk + EFFORT_SPAN * work, 4)



def build(peaks_csv: str, routes_csv: str, combos_csv: str, out_json: str) -> None:
    peaks = []
    with open(peaks_csv) as f:
        for row in csv.DictReader(f):
            peaks.append({
                "rank": int(row["rank"]) if row["rank"] else None,
                "name": row["name"],
                "elevation_ft": int(row["elevation_ft"]),
                "range": row["range"],
                "peak_id": row["peak_id"],
                "slug": row["slug"],
                "note": row.get("note", ""),
                "unranked": row["rank"] == "",
                "routes": [],
            })

    names_by_slug = {p["slug"]: p["name"] for p in peaks}
    routes_by_peak = defaultdict(list)
    with open(routes_csv) as f:
        route_rows = [row for row in csv.DictReader(f)
                      if row["difficulty"] not in ("false", "true", "")]
    maxima = rating_maxima(route_rows)
    effort = effort_maxima(route_rows)
    combo_summits = load_combo_summits(combos_csv)
    dropped = 0
    for row in route_rows:
            kind = row_kind(row, combo_summits)
            if kind is None:
                dropped += 1
                continue
            routes_by_peak[row["peak_id"]].append({
                "kind": kind,
                "name": row["route_name"],
                "is_standard": row["is_standard"] == "true",
                "is_snow_climb": row["is_snow_climb"] == "true",
                "is_primary": row["is_primary_for_peak"] == "true",
                "difficulty": row["difficulty"],
                "gain": row["elevation_gain"],
                "distance": row["distance"],
                "exposure": row["exposure"],
                "rockfall": row["rockfall"],
                "route_finding": row["route_finding"],
                "commitment": row["commitment"],
                "route_key": row["route_key"],
                "summits": summits_label(row, kind, combo_summits, names_by_slug),
                "road": int(row["road_difficulty"]) if row.get("road_difficulty") else None,
                "trailhead": row.get("trailhead_name") or None,
                "th_lat": float(row["trailhead_lat"]) if row.get("trailhead_lat") else None,
                "th_lon": float(row["trailhead_lon"]) if row.get("trailhead_lon") else None,
                "score": difficulty_score(row, maxima, effort),
            })

    for p in peaks:
        p["routes"] = routes_by_peak.get(p["peak_id"], [])
        p["routes"].sort(key=lambda r: (KIND_ORDER[r["kind"]], not r["is_standard"],
                                        not r["is_primary"], r["difficulty"]))

    with open(out_json, "w") as f:
        json.dump(peaks, f, separators=(",", ":"))

    ranked = sum(1 for p in peaks if not p["unranked"])
    kinds = defaultdict(int)
    for p in peaks:
        for r in p["routes"]:
            kinds[r["kind"]] += 1
    print(f"wrote {out_json}: {ranked} ranked peaks, "
          f"{len(peaks) - ranked} subpoints, "
          f"{kinds[KIND_ROUTE]} routes, {kinds[KIND_COMBO]} combos, "
          f"{kinds[KIND_APPROACH]} approaches "
          f"({os.path.getsize(out_json):,} bytes)")
    print(f"dropped {dropped} rows belonging to other peaks in the same area")


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(here)
    ap = argparse.ArgumentParser(description="Build peaks.json from CSVs.")
    ap.add_argument("--peaks", default=os.path.join(repo, "data", "colorado_14ers_peaks.csv"))
    ap.add_argument("--routes", default=os.path.join(repo, "data", "colorado_14ers_routes.csv"))
    ap.add_argument("--combos", default=os.path.join(repo, "data", "combo_summits.csv"))
    ap.add_argument("--out", default=os.path.join(repo, "peaks.json"))
    args = ap.parse_args()

    for path, label in [(args.peaks, "peaks"), (args.routes, "routes")]:
        if not os.path.exists(path):
            print(f"missing {label} csv: {path}", file=sys.stderr)
            return 1

    build(args.peaks, args.routes, args.combos, args.out)
    print("next: run scripts/embed_data.py to inline this JSON into index.html.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
