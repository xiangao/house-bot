# house-bot

Daily house listing monitor using Redfin's unofficial API.

## Setup

1. Copy `.env.example` to `.env` and fill in Gmail credentials (use an App Password)
2. `test -d .venv || python3 -m venv .venv`
3. `source .venv/bin/activate && pip install -r requirements.txt`
4. `python main.py` to run manually

## Systemd Timer (daily at 9am)

```bash
mkdir -p ~/.config/systemd/user
cp house-bot.service house-bot.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now house-bot.timer
```

Logs: `journalctl --user -u house-bot.service`

## Config

`config/searches.yaml` — towns, price range ($900K–$1.5M), bed/bath minimums (3+/2+).
The header label on the dashboard is derived from `min_price`/`max_price` at
render time (passed into `html_writer.write_html`), so it can't drift from config.

## Output

- `data/listings.csv` — all seen listings with first_seen / last_price for change detection
- `output/latest.txt` — last run summary (new listings + price drops)
- `output/listings.html` — dashboard. Opens with a **🆕 New in last N days**
  section (`html_writer.NEW_WINDOW_DAYS`, default 7) built from each row's
  `first_seen` date. The new section is grouped by town (`<h3>` sub-headings,
  same order as the full sections, towns with no new listings omitted),
  newest-first within each town. Listings inside the New window are **not**
  duplicated below: each per-town section in `render_page` filters out rows
  where `_is_new(row, cutoff)` is true, so a listing lives in the New section
  until it ages past `NEW_WINDOW_DAYS`, then moves down into its town section.
  A town whose listings are all still "new" is omitted from the lower sections
  (it's fully represented up top). When there are no new listings the filter
  removes nothing and every town section shows its full set.

## Commuter-rail distance

Each listing shows the **driving distance to the nearest MBTA commuter rail
station** (`🚆 X.X mi · Y min by car to <station>` on the card and in the email).

Pipeline (`code/transit.py`, called from `main.py` after remarks enrichment):
1. House lat/lon come straight from the Redfin CSV (`LATITUDE`/`LONGITUDE`,
   parsed in `searcher.py`).
2. `nearest_station_by_car()` haversine-ranks the vendored stations, keeps the
   `CANDIDATE_K` (=4) nearest as-the-crow-flies, then road-routes to only those
   via the **OSRM public demo** (`router.project-osrm.org`, no API key) and keeps
   the minimum driving distance. The straight-line prefilter avoids routing to
   all ~148 stations.
3. Result cached in the CSV (`nearest_station`, `station_miles`,
   `station_minutes`) so each house is routed at most once, ever — same pattern
   as remarks. Coordinates refresh each run; the routed distance does not.

Station coordinates are vendored in `code/mbta_commuter_rail_stations.json`
(148 unique stations, MBTA v3 API `route_type=2`, deduped by name) — no runtime
MBTA dependency. Regenerate only if stations change. Listings without
coordinates (e.g. delisted rows retained by the never-prune behavior) show no
distance.

## Alert Logic

- **New listing**: listing_id not in data/listings.csv → email
- **Price drop**: same listing_id, price decreased since last run → email
- No email if nothing changed

## Builder-Owned Detection

Listings flagged as "builder's own home" (homes builders construct for
themselves) get a 🔨 badge in `output/listings.html`. No email/alert change.

Pipeline:
1. `searcher.fetch_remarks(session, url)` extracts the MLS marketing remarks
   text from the listing HTML (`<div id="marketing-remarks-scroll">`). Used
   because Redfin's `belowTheFold` JSON API is WAF-blocked even with
   `curl_cffi` impersonation, but the public HTML page returns 200.
2. `searcher.enrich_remarks(listings, known)` fetches remarks only for
   listings not yet cached in `data/listings.csv`. So each listing costs one
   extra HTTP exactly once across all runs.
3. `code/classifier.py::is_builder_owned(remarks, year_built)` is a pure
   regex-based classifier — edit this file to tune patterns. Re-runs on every
   listing every run, so changing patterns re-classifies the whole CSV next
   night.

CSV columns added: `remarks` (cached text), `builder_owned` ("1"/""),
`builder_match` (the snippet that matched, for audit).

## API

Uses Redfin unofficial GIS-CSV endpoint. No API key required.
- Autocomplete: `stingray/do/location-autocomplete` resolves town → region_id
- Listings: `stingray/api/gis-csv` returns CSV of matching listings

### Anti-bot (AWS WAF / CloudFront)

Redfin sits behind AWS WAF, which JA3/JA4-fingerprints the TLS ClientHello and
returns `403 Request blocked` to plain `requests` *at the handshake* — before any
header/cookie is read (verified 2026-06-01: same IP, `curl` → 200, `requests` → 403).
`code/searcher.py` therefore uses **`curl_cffi` with `Session(impersonate="chrome")`**
to present a real Chrome TLS fingerprint. Header tweaks alone do nothing.
If 403s return, bump the `_IMPERSONATE` Chrome target in `code/searcher.py`.

## Interactive dashboard

### Architecture

`code/app.py` is a Flask app that serves an interactive dashboard on the home LAN. It is always-on, managed by `house-bot-dashboard.service` (separate from the nightly `house-bot.timer`). Entry point: `python -m code.app` or `code.app:main`. The factory function is `create_app(csv_path, db_path, tax_rates, min_price, max_price)` — used directly in tests and in `main()`.

Key files:
- `code/app.py` — Flask routes: `GET /`, `GET /api/annotations`, `POST /api/annotations/<listing_id>`
- `code/annotations.py` — SQLite helpers (`init_db`, `upsert`, `get_all`); `STATUS_LABELS` list
- `data/annotations.db` — SQLite DB on disk; gitignored, never pushed
- `house-bot-dashboard.service` — systemd unit; copy to `~/.config/systemd/user/` to enable

### Enabling the service

```bash
cp house-bot-dashboard.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now house-bot-dashboard.service
# logs: journalctl --user -u house-bot-dashboard.service
```

The dashboard port is set by `dashboard.port` in `config/searches.yaml` (default 8000). It binds `0.0.0.0` so it is reachable from any device on the LAN. No authentication — trusted LAN only.

### Annotations

Status labels (defined in `annotations.STATUS_LABELS`): Favorite, Favorite but pending, Interested, Interested but pending, Worth visiting, Visited, Touring scheduled, Maybe, Rejected. The "but pending" labels are manual user sentiment and are independent of the automatic Redfin "Sale pending" badge (which is driven by the `status` column). Each label gets a colored left border in `_CSS`; the "but pending" variants reuse their base color with a dashed border. Stored in `data/annotations.db`; loaded into `render_page()` via the `annotations=` kwarg. The interactive flag (`interactive=True`) enables the dropdown/note controls in the rendered HTML; the nightly static build uses `interactive=False`.

Both household browsers hit the same server and DB, so annotations are shared in real time. The "Show:" filter is rendered client-side (JS is the `page_js` string inside `render_page` in `code/html_writer.py`; styles are in the module-level `_CSS` constant in the same file).

### Sale pending

`main.py` issues a second Redfin GIS-CSV query (`status=130`) after the active search. Results are merged only for listing IDs already present in `data/listings.csv` (previously Active) — strangers' pending listings are never imported. Merged rows get `status="Pending"` or `status="Contingent"`. `html_writer.render_page` dims these cards and shows a badge. If a pending listing later returns Active, the status column resets and the badge clears on the next render.

### Public mirror and annotations privacy

`mirror_annotations` in `config/searches.yaml` controls what the nightly bot bakes into the GitHub Pages static copy:
- `full` — labels + notes (world-readable; notes are published publicly)
- `labels` — labels only; notes stay local
- `none` — no annotation data in the public copy

The annotation POST API is only reachable on the LAN. The public mirror is view-only.
