# Interactive house-bot: annotations + sale-pending

**Date:** 2026-06-08
**Status:** Approved design — ready for implementation plan

## Goal

Two additions to house-bot:

1. **Annotations.** While browsing the dashboard, the user (and their spouse) can
   tag each house with a **status label** (Favorite / Worth visiting / Visited /
   Touring scheduled / Maybe / Rejected) and a **free-text note**. Annotations
   are shared between both people and persist across nightly regenerations.
2. **Sale-pending label.** When a tracked house goes under contract on Redfin,
   it is shown with a "Sale pending" badge and a dimmed card (not hidden), so it
   stays visible in case the deal falls through.

## Decisions (from brainstorming)

| Question | Decision |
|----------|----------|
| Annotation persistence | Real backend (not localStorage) |
| Where the backend runs | Self-hosted on the desktop (where the bot already runs) |
| Reachability | Home WiFi only (no Tailscale / public tunnel) |
| What an annotation is | Status label + free-text note (no attribution, no rating) |
| Multi-user | Both spouses hit the same server → one shared SQLite DB |
| Pending behavior | Show, badged + de-emphasized (dimmed card) |
| Public GitHub Pages mirror | Keep it as a read-only baked copy |
| Status label set | Favorite / Worth visiting / Visited / Touring scheduled / Maybe / Rejected |
| What gets baked into the public mirror | Labels **and** notes (configurable; see Privacy) |
| Web framework | Flask |

## Architecture

Two cooperating parts that share `data/listings.csv` (one writer) and nothing else:

```
nightly (systemd .timer, 9:30am)          always-on (systemd .service)
  main.py                                   code/app.py  (Flask, 0.0.0.0:PORT)
   search Redfin (active + pending)           GET  /            → render dashboard (interactive)
   → data/listings.csv (+ status col)         GET  /api/annotations
   bake annotations into static HTML          POST /api/annotations/<mls#>
   → push read-only mirror to GitHub Pages   reads listings.csv; reads+writes data/annotations.db
```

- **Writer separation:** the bot owns `listings.csv` (nightly writes); the app
  owns `annotations.db` (writes on click). They never write the same file, so the
  timer and the live app never contend. The app only *reads* `listings.csv`.
- **One render function, two callers:** `html_writer.write_html` gains an
  `annotations` dict and an `interactive: bool` flag. The local app renders
  per-request with `interactive=True` (live controls). The bot renders the static
  mirror with `interactive=False` (read-only labels/notes). No duplicated layout.

## Data stores

### `data/listings.csv` (existing, +1 column)

Add `status` column: one of `Active`, `Pending`, `Contingent`. Populated from
Redfin's `STATUS` column (verified present in the GIS-CSV response). Appended to
`analyzer.CSV_FIELDS` and refreshed every run like other live fields.

### `data/annotations.db` (NEW, SQLite, gitignored)

```sql
CREATE TABLE IF NOT EXISTS annotations (
  listing_id   TEXT PRIMARY KEY,   -- MLS#
  status_label TEXT,               -- "" or one of the 6 labels
  note         TEXT,               -- free text, "" if none
  updated_at   TEXT                -- ISO timestamp
);
```

SQLite (stdlib `sqlite3`, no new storage dependency) is chosen over a JSON file
specifically because two browsers may save concurrently; SQLite serializes
writes, a JSON file risks a lost update where one spouse's save clobbers the
other's.

## Feature 1 — annotations

**Status labels (fixed list, edit in code):**
`Favorite`, `Worth visiting`, `Visited`, `Touring scheduled`, `Maybe`,
`Rejected`, plus implicit "none" (empty).

**Rendering (each card):**
- `data-listing-id="<mls#>"` on the card root.
- A `<select>` bound to the status label and a small note `<textarea>`.
- Server-side renders the *current* annotation into the controls so labels and
  notes appear even before JS runs / with JS disabled.
- The status label drives a colored left-border + a chip on the card.

**Editing (JS on the page):**
- On `<select>` change → immediate `POST /api/annotations/<mls#>`.
- On note edit → debounced autosave (~800 ms) `POST` of the same endpoint.
- Optimistic UI: recolor the card on change; on POST failure, show a small
  inline "save failed" marker and keep the value (no data loss).

**Filter control (top of page, client-side):**
- "Show only: [All ▾]" over the label set; hides non-matching cards in the DOM.
- Pure client-side over already-rendered cards; no server round-trip.

## Feature 2 — sale pending

**Fetch.** `searcher` gains a second GIS-CSV call per town with `status=130`
(returns `Pending` + `Contingent`), parsing the `STATUS` column. The existing
active call keeps `status=1`.

**Scope guard (important).** The pending query returns the town's *entire*
under-contract inventory (~80–100 listings/town). We do **not** import all of it.
A listing is flipped to pending only if it is **already tracked** (present in
`listings.csv` from a prior active run). The signal is "a house *you were
watching* went under contract," not a flood of strangers' pending homes. A house
discovered for the first time already pending is skipped (acceptable).

**Fall-through.** If a pending deal collapses, the listing reappears in the
`status=1` active query and its status flips back to `Active`; badge and dimming
are removed automatically.

**Rendering.** Cards with status `Pending`/`Contingent` get:
- a **"Sale pending" badge** (reusing the existing badge pipeline that
  builder-owned uses), and
- a `card-pending` CSS class that dims the card (reduced opacity / muted), while
  remaining visible and still annotatable.

## GitHub Pages read-only mirror

The nightly bot, after writing `listings.csv`, renders the static dashboard with
`interactive=False`, baking in current annotations, and pushes to gh-pages as
today (`main._deploy`). Remote viewers see status labels and notes but cannot
edit (no controls; no backend reachable off-LAN).

**Privacy caveat.** The gh-pages mirror is world-readable. Baking free-text notes
publishes them publicly. The bake scope is a config flag
`mirror_annotations: full | labels | none` (default `full`, per decision) so it
can be narrowed to labels-only or disabled without a code change.

## Running it

- New systemd **user service** `house-bot-dashboard.service` — a long-running
  Flask process bound to `0.0.0.0:<PORT>` so LAN devices reach it. Distinct from
  the existing `house-bot.timer` (nightly fetch).
- **No authentication** — trusted home LAN, by explicit choice.
- Port configurable; documented in README/CLAUDE.md.

## Module changes

| File | Change |
|------|--------|
| `code/searcher.py` | add `status` field to `Listing`; add pending fetch (`status=130`) per town; parse `STATUS` column |
| `code/analyzer.py` | add `status` to `CSV_FIELDS`; save/refresh it; restrict pending-merge to known listings |
| `code/annotations.py` | **NEW** — `init_db()`, `get_all()`, `upsert(listing_id, status_label, note)` |
| `code/html_writer.py` | `annotations` + `interactive` params; `data-listing-id`, controls, client-side filter, pending badge + `card-pending` dim; JS + CSS |
| `code/app.py` | **NEW** — Flask app; `GET /`, `GET /api/annotations`, `POST /api/annotations/<mls#>` |
| `main.py` | pending merge (known-only); pass annotations + `mirror_annotations` scope into the mirror render |
| `config/searches.yaml` | add `dashboard.port` and `mirror_annotations` settings |
| `requirements.txt` | add `flask` |
| `house-bot-dashboard.service` | **NEW** systemd unit |
| `.gitignore` | add `data/annotations.db` |
| `CLAUDE.md`, `README.md` | document the app, the service, status labels, mirror privacy |

## Out of scope (YAGNI)

Per-person attribution, star/thumbs rating, real authentication, cloud or
off-network access, and importing the full pending inventory — all dropped based
on the brainstorming answers.

## Risks / open notes

- **Pending query value `130`** is empirically derived (returns Pending +
  Contingent in the probed towns). Implementation should treat the `STATUS`
  column as the source of truth and tolerate other/unknown status strings
  (default to "shown normally").
- **Public notes** — see Privacy caveat above; default honors the user's choice.
- **Desktop must be awake** for annotating; accepted tradeoff of self-hosting.
- **Concurrent edits to the same house** by both spouses: last write wins on a
  per-field POST. Acceptable for two cooperating users.
