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
import sys
from collections import defaultdict


def build(peaks_csv: str, routes_csv: str, out_json: str) -> None:
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

    routes_by_peak = defaultdict(list)
    with open(routes_csv) as f:
        for row in csv.DictReader(f):
            if row["difficulty"] in ("false", "true", ""):
                continue
            routes_by_peak[row["peak_id"]].append({
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
                "summits": row["route_summits"],
                "road": int(row["road_difficulty"]) if row.get("road_difficulty") else None,
            })

    for p in peaks:
        p["routes"] = routes_by_peak.get(p["peak_id"], [])
        p["routes"].sort(key=lambda r: (not r["is_standard"], not r["is_primary"], r["difficulty"]))

    with open(out_json, "w") as f:
        json.dump(peaks, f, separators=(",", ":"))

    ranked = sum(1 for p in peaks if not p["unranked"])
    routes = sum(len(p["routes"]) for p in peaks)
    print(f"wrote {out_json}: {ranked} ranked peaks, "
          f"{len(peaks) - ranked} subpoints, {routes} routes "
          f"({os.path.getsize(out_json):,} bytes)")


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    repo = os.path.dirname(here)
    ap = argparse.ArgumentParser(description="Build peaks.json from CSVs.")
    ap.add_argument("--peaks", default=os.path.join(repo, "data", "colorado_14ers_peaks.csv"))
    ap.add_argument("--routes", default=os.path.join(repo, "data", "colorado_14ers_routes.csv"))
    ap.add_argument("--out", default=os.path.join(repo, "peaks.json"))
    args = ap.parse_args()

    for path, label in [(args.peaks, "peaks"), (args.routes, "routes")]:
        if not os.path.exists(path):
            print(f"missing {label} csv: {path}", file=sys.stderr)
            return 1

    build(args.peaks, args.routes, args.out)
    print("next: run scripts/embed_data.py to inline this JSON into index.html.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
