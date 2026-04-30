# Colorado 14ers

Quick-reference site for the 53 ranked Colorado 14,000 ft peaks. Built from data scraped off [14ers.com](https://14ers.com).

Use case: someone says "let's climb La Plata" and you want to know in 10 seconds how hard it is and what the route options look like.

## Features

- Sortable, filterable peak table (by range, max class, snow ok / not, search)
- Click a peak to see all its routes with difficulty, gain, distance, exposure / rockfall / route-finding / commitment ratings
- Route names link out to the 14ers.com route page
- Personal summit tracker — checkbox per peak, persisted in `localStorage`. Counter shows X / 53 summited
- Single-file static site, no build step, no backend, no fetch races (data is inline)

## Files

- `index.html` — the whole site. Open it directly in a browser.
- `peaks.json` — same data as embedded in `index.html`, kept around for re-use.

## Hosting on GitHub Pages

```
git init
git add .
git commit -m "co-14ers v0.1"
git branch -M main
git remote add origin git@github.com:<you>/co-14ers.git
git push -u origin main
```

In repo settings → Pages → deploy from `main` / root. URL will be `https://<you>.github.io/co-14ers/`.

## Updating the data

Re-run the scraper, drop new CSVs in, re-run the conversion (see project notes), then regenerate `index.html`.

## License / attribution

Data is from 14ers.com. This is for personal reference; respect their terms.
