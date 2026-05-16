# Colorado 14ers

Quick-reference site for the 53 ranked Colorado 14,000 ft peaks, built
from data scraped off [14ers.com](https://14ers.com).

[Live →](https://siriusganesh.github.io/co-14ers/)

Use case: someone says "let's climb La Plata" and you want to know in
10 seconds how hard it is and what the route options look like.

## Features

- Sortable, filterable peak table (range, max class, snow ok / not, search).
- Click a peak to see all its routes with difficulty, gain, distance,
  exposure / rockfall / route-finding / commitment ratings.
- Route names link out to the 14ers.com route page.
- Account-backed tracker (Supabase) — summits with date, route-line
  checkmarks, planned-trips list. Private to your account.
- localStorage fallback when signed-out; first sign-in migrates anything
  tracked locally.

## Deliberate choices

- Single-file `index.html` for the whole app — peaks data inlined at
  build time so the page loads in one request.
- Supabase Auth + Postgres RLS on every table; the localStorage shim
  mirrors the same shape so the UI is identical signed-in vs out.
- CSV → JSON → inlined-into-HTML pipeline via idempotent Python scripts
  (`build_data.py`, `embed_data.py`).
- Lighthouse CI on every PR (mobile + desktop matrix).

## Updating the data

```
python3 scripts/build_data.py    # CSVs in data/ → peaks.json
python3 scripts/embed_data.py    # peaks.json → inlined in index.html
git commit -am "data: refresh from 14ers.com YYYY-MM-DD"
git push                          # GitHub Pages auto-deploys from main
```

Supabase setup walkthrough: `docs/setup-supabase.md`.
Auth architecture: `docs/auth-design.md`.

## Attribution

Data scraped from 14ers.com. Personal reference only — respect their terms.
