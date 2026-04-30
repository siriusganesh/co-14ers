# Colorado 14ers

Quick-reference site for the 53 ranked Colorado 14,000 ft peaks. Built from data scraped off [14ers.com](https://14ers.com).

Live: https://siriusganesh.github.io/co-14ers/

Use case: someone says "let's climb La Plata" and you want to know in 10 seconds how hard it is and what the route options look like.

## Features

- Sortable, filterable peak table (by range, max class, snow ok / not, search)
- Click a peak to see all its routes with difficulty, gain, distance, exposure / rockfall / route-finding / commitment ratings
- Route names link out to the 14ers.com route page
- Account-backed tracker (Supabase) — summits with date, route-line checkmarks, and a planned-trips list, all private to your account
- Falls back to `localStorage` when signed-out; first sign-in migrates anything tracked locally

## Files

```
index.html              # the whole app
reset.html              # password recovery landing
peaks.json              # data file (also inlined in index.html)
data/
  colorado_14ers_peaks.csv   # source (from 14ers.com scrape)
  colorado_14ers_routes.csv  # source
scripts/
  build_data.py        # CSVs -> peaks.json
  embed_data.py        # peaks.json -> inline literal in index.html
supabase/
  schema.sql           # tables + RLS policies (paste into Supabase SQL editor)
docs/
  auth-design.md       # architecture
  setup-supabase.md    # one-time project setup
```

## Hosting

Already live on GitHub Pages at https://siriusganesh.github.io/co-14ers/, served from `main` / root. Deploy is automatic — every push to `main` triggers a Pages build, which usually finishes within a minute.

If Pages ever needs to be re-enabled or re-pointed, that's in the repo's Settings → Pages.

## Updating the data

```
# 1. drop new CSVs into data/
cp ~/wherever/colorado_14ers_peaks.csv  data/
cp ~/wherever/colorado_14ers_routes.csv data/

# 2. rebuild peaks.json from the CSVs
python3 scripts/build_data.py

# 3. inline the JSON into index.html (the live site reads from there, not from peaks.json)
python3 scripts/embed_data.py

# 4. ship it
git add data peaks.json index.html
git commit -m "data: refresh from 14ers.com YYYY-MM-DD"
git push
```

`build_data.py` filters out malformed difficulty rows and sorts each peak's routes (standard route first, then primary, then by class). Both scripts are idempotent.

## License / attribution

Data is from 14ers.com. This is for personal reference; respect their terms.
