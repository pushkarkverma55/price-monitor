# Laptop Price Monitor (Amazon.in)

Zero-cost price & variant monitoring: a Python scraper on my Mac snapshots Amazon.in laptop
listings every 6 hours, discovers variant siblings (same model line, different RAM/storage/CPU)
from Amazon's own variation data, stores history in SQLite, and publishes JSON + a static React
dashboard to GitHub Pages.

**Dashboard:** https://pushkarkverma55.github.io/price-monitor/

## How it works

```
launchd (every 6h)
  └─ run.sh
      ├─ scraper/main.py   Playwright (headless Chromium) fetches search + product pages
      │                    → parse price/MRP/rating/stock + twister variant siblings
      │                    → SQLite (data/pricemonitor.db, source of truth, local only)
      │                    → export docs/data/{catalog,history,meta}.json
      └─ git commit + push docs/data  → GitHub Pages serves dashboard + fresh data
```

- `scraper/` — fetcher (Playwright), parsers (regex over page HTML + embedded twister JSON),
  spec extraction (brand / model line / RAM / storage / CPU from titles), SQLite + JSON export.
- `dashboard/` — Vite + React + Tailwind + recharts. Builds into `docs/`. Reads `./data/*.json`.
- `docs/` — GitHub Pages root: built dashboard + exported data.
- `scraper/config.json` — search queries, allowed brands, product cap, pacing.

## Commands

```sh
.venv/bin/python -m scraper.main              # full run: seed from search + snapshot everything
.venv/bin/python -m scraper.main --no-search  # snapshot known products only
./run.sh                                      # what launchd runs (scrape + export + git push)
cd dashboard && npm run dev                   # dashboard dev server
cd dashboard && npm run build                 # build dashboard → docs/
launchctl load ~/Library/LaunchAgents/com.pushkar.pricemonitor.plist    # enable schedule
launchctl unload ~/Library/LaunchAgents/com.pushkar.pricemonitor.plist  # disable
```

## Adding products

Add search queries to `scraper/config.json` (`search_queries`) and brands to `allowed_brands`.
Variant siblings of anything found are tracked automatically. Cap: `max_products`.

## Notes

- Price history accumulates from the day a product is first tracked — there is no backfill.
- The Mac must be awake for a scheduled run to happen; launchd runs the missed job when it's next up.
- Scraping Amazon is against their ToS; this is low-volume personal monitoring (~few hundred
  pages/day, 3–6 s between requests). Selectors will rot occasionally; fixes live in `scraper/parse.py`.
