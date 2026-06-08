# Interactive house-bot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-house annotations (status label + note) editable from a local Flask app on the home LAN, plus a Redfin "Sale pending" badge, while keeping the nightly bot and its read-only GitHub Pages mirror working.

**Architecture:** A new always-on Flask app (`code/app.py`) serves the dashboard live from `data/listings.csv` + `data/annotations.db` (SQLite) and accepts annotation edits. The existing nightly `main.py` gains sale-pending detection and bakes annotations into the static mirror it pushes to GitHub Pages. The two processes share `listings.csv` (bot writes, app reads) but write different files, so they never contend.

**Tech Stack:** Python 3, Flask, stdlib `sqlite3`, curl_cffi (existing), pytest (new, for tests).

**Design doc:** `docs/superpowers/specs/2026-06-08-house-bot-interactive-design.md`

**Conventions for this repo:**
- Imports use the `code` package: `from code.searcher import Listing`.
- Run tests from the repo root: `source .venv/bin/activate && python -m pytest`.
- Install missing deps with `uv pip install <pkg>` (do not reinstall existing).
- Commit messages: imperative subject; this work lives on branch `interactive-annotations`.

---

## File Structure

| File | Responsibility |
|------|----------------|
| `code/annotations.py` | **NEW** — SQLite annotation store + the canonical `STATUS_LABELS` list |
| `code/searcher.py` | add `Listing.status`; parse `STATUS` column; `fetch_pending_map()` |
| `code/analyzer.py` | add `status` to `CSV_FIELDS`; persist it; apply pending map to known-only rows |
| `code/html_writer.py` | extract `render_page() -> str`; card annotations + pending badge/dim; CSS + JS |
| `code/app.py` | **NEW** — Flask app: serve dashboard + annotations API |
| `main.py` | wire pending fetch + mirror render with annotation scope |
| `config/searches.yaml` | add `dashboard.port` and `mirror_annotations` |
| `house-bot-dashboard.service` | **NEW** — systemd unit for the always-on app |
| `requirements.txt`, `.gitignore` | add `flask`, `pytest`; ignore `data/annotations.db` |
| `tests/` | **NEW** — pytest suite |
| `CLAUDE.md`, `README.md` | document the app, service, labels, privacy |

---

## Task 1: Test infra + annotation store (SQLite)

**Files:**
- Create: `code/annotations.py`
- Create: `tests/__init__.py` (empty)
- Create: `tests/test_annotations.py`

- [ ] **Step 1: Install test + web deps (missing only)**

```bash
cd ~/projects/claude/house-bot && source .venv/bin/activate
uv pip install flask pytest
```

- [ ] **Step 2: Write the failing test**

Create `tests/__init__.py` (empty file) and `tests/test_annotations.py`:

```python
from pathlib import Path

from code import annotations as ann


def test_upsert_then_get(tmp_path: Path):
    db = tmp_path / "ann.db"
    ann.upsert(db, "MLS123", "Worth visiting", "great kitchen")
    got = ann.get_all(db)
    assert got["MLS123"]["status_label"] == "Worth visiting"
    assert got["MLS123"]["note"] == "great kitchen"
    assert got["MLS123"]["updated_at"]  # non-empty timestamp


def test_upsert_updates_existing(tmp_path: Path):
    db = tmp_path / "ann.db"
    ann.upsert(db, "MLS123", "Maybe", "")
    ann.upsert(db, "MLS123", "Rejected", "too small")
    got = ann.get_all(db)
    assert len(got) == 1
    assert got["MLS123"]["status_label"] == "Rejected"
    assert got["MLS123"]["note"] == "too small"


def test_get_all_missing_db_is_empty(tmp_path: Path):
    assert ann.get_all(tmp_path / "nope.db") == {}


def test_status_labels_is_the_agreed_set():
    assert ann.STATUS_LABELS == [
        "Favorite", "Worth visiting", "Visited",
        "Touring scheduled", "Maybe", "Rejected",
    ]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_annotations.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'code.annotations'`

- [ ] **Step 4: Write the implementation**

Create `code/annotations.py`:

```python
"""SQLite-backed store for per-listing annotations (status label + free note).

This is the live source of truth for user annotations, written by the Flask
app (code/app.py) on every click and read by both the app and the nightly
bot (which bakes annotations into the static GitHub Pages mirror). It is kept
separate from data/listings.csv so the always-on app and the nightly bot
never write the same file.
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

# Canonical status-label vocabulary. Edit here to change the pick-list; the
# Flask app validates against this list and html_writer renders options from it.
STATUS_LABELS = [
    "Favorite", "Worth visiting", "Visited",
    "Touring scheduled", "Maybe", "Rejected",
]


def init_db(db_path: Path) -> None:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS annotations (
                listing_id   TEXT PRIMARY KEY,
                status_label TEXT NOT NULL DEFAULT '',
                note         TEXT NOT NULL DEFAULT '',
                updated_at   TEXT NOT NULL DEFAULT ''
            )"""
        )


def get_all(db_path: Path) -> dict[str, dict]:
    """Return {listing_id: {status_label, note, updated_at}} (empty if no DB)."""
    db_path = Path(db_path)
    if not db_path.exists():
        return {}
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT listing_id, status_label, note, updated_at FROM annotations"
        ).fetchall()
    return {r["listing_id"]: dict(r) for r in rows}


def upsert(db_path: Path, listing_id: str, status_label: str, note: str) -> None:
    init_db(db_path)
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """INSERT INTO annotations (listing_id, status_label, note, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(listing_id) DO UPDATE SET
                   status_label = excluded.status_label,
                   note         = excluded.note,
                   updated_at   = excluded.updated_at""",
            (listing_id, status_label, note, ts),
        )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_annotations.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
git add code/annotations.py tests/__init__.py tests/test_annotations.py requirements.txt
git commit -m "Add SQLite annotation store + status-label vocabulary"
```

(Note: also add `flask` and `pytest` to `requirements.txt` in this commit — see Task 10 Step for the exact final file; adding them now is fine.)

---

## Task 2: Parse Redfin STATUS into Listing.status

**Files:**
- Modify: `code/searcher.py` (`Listing` dataclass ~line 27; `_parse_row` ~line 122)
- Create: `tests/test_searcher_status.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_searcher_status.py`:

```python
from code.searcher import _parse_row

BASE_ROW = {
    "SALE TYPE": "MLS Listing",
    "PROPERTY TYPE": "Single Family Residential",
    "ADDRESS": "1 Main St",
    "CITY": "Natick",
    "STATE OR PROVINCE": "MA",
    "ZIP OR POSTAL CODE": "01760",
    "PRICE": "$1,000,000",
    "BEDS": "3",
    "BATHS": "2",
    "SQUARE FEET": "2,000",
    "YEAR BUILT": "1990",
    "DAYS ON MARKET": "5",
    "MLS#": "73000001",
    "LATITUDE": "42.28",
    "LONGITUDE": "-71.35",
}


def test_parse_row_reads_status():
    row = {**BASE_ROW, "STATUS": "Pending"}
    listing = _parse_row(row, "Natick, MA")
    assert listing is not None
    assert listing.status == "Pending"


def test_parse_row_status_defaults_empty():
    row = dict(BASE_ROW)  # no STATUS key
    listing = _parse_row(row, "Natick, MA")
    assert listing.status == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_searcher_status.py -v`
Expected: FAIL — `AttributeError: 'Listing' object has no attribute 'status'`

- [ ] **Step 3: Add the field to the dataclass**

In `code/searcher.py`, in the `Listing` dataclass, add after the `year_built` line (before `latitude`):

```python
    # Redfin listing status ("Active", "Pending", "Contingent", ...). Refreshed
    # each run; drives the "Sale pending" badge + dimmed card in html_writer.
    status: str = ""
```

- [ ] **Step 4: Populate it in `_parse_row`**

In `code/searcher.py`, in `_parse_row`, in the `return Listing(...)` call, add (e.g. right after `town=town,`):

```python
        status=(row.get("STATUS") or "").strip(),
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_searcher_status.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add code/searcher.py tests/test_searcher_status.py
git commit -m "Parse Redfin STATUS column into Listing.status"
```

---

## Task 3: Fetch pending/contingent listings (status=130)

**Files:**
- Modify: `code/searcher.py` (add `fetch_pending_map` near `search_all`, end of file)

This function reuses `search_town` with `status=130` (empirically returns Pending +
Contingent for the search criteria). No unit test for the network call (mirrors
the existing untested `search_all`); it is exercised by the manual smoke test in
Task 11. Keep it small and obviously correct.

- [ ] **Step 1: Implement `fetch_pending_map`**

In `code/searcher.py`, append after `search_all`:

```python
def fetch_pending_map(config: dict) -> dict[str, str]:
    """Return {mls#: status_label} for Pending/Contingent listings matching the
    search criteria across all towns (Redfin status=130).

    Used only to flag listings we are ALREADY tracking that have gone under
    contract — the caller (analyzer.save_listings) intersects this with known
    listings and never imports new pending homes.
    """
    session = _session()
    session.get("https://www.redfin.com/", timeout=15)
    time.sleep(1.0)

    search_cfg = dict(config["search"])
    search_cfg["status"] = 130

    pending: dict[str, str] = {}
    for town_cfg in config["towns"]:
        try:
            listings = search_town(
                session, town_cfg, search_cfg,
                town_cfg["region_id"], town_cfg["region_type"],
            )
            for l in listings:
                pending[l.listing_id] = l.status or "Pending"
        except Exception as e:
            print(f"  WARNING pending [{town_cfg['name']}]: {e}")
        time.sleep(1.0)
    return pending
```

- [ ] **Step 2: Sanity-check it imports**

Run: `python -c "from code.searcher import fetch_pending_map; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add code/searcher.py
git commit -m "Add fetch_pending_map (Redfin status=130) for under-contract listings"
```

---

## Task 4: Persist status + apply pending map to known listings only

**Files:**
- Modify: `code/analyzer.py` (`CSV_FIELDS` ~line 8; `save_listings` ~line 39)
- Create: `tests/test_pending_merge.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_pending_merge.py`:

```python
import csv
from pathlib import Path

from code.analyzer import save_listings, CSV_FIELDS
from code.searcher import Listing


def _make_known(listing_id: str) -> dict:
    # A previously-seen active listing as load_known would return it.
    return {
        listing_id: {f: "" for f in CSV_FIELDS} | {
            "listing_id": listing_id, "town": "Natick, MA",
            "price": "1000000", "last_price": "1000000",
            "first_seen": "2026-06-01", "last_seen": "2026-06-01",
        }
    }


def _read(csv_path: Path) -> dict[str, dict]:
    with open(csv_path, newline="") as f:
        return {r["listing_id"]: r for r in csv.DictReader(f)}


def test_status_field_in_csv_fields():
    assert "status" in CSV_FIELDS


def test_pending_applies_to_known_only(tmp_path: Path):
    csv_path = tmp_path / "listings.csv"
    known = _make_known("TRACKED")
    pending_map = {"TRACKED": "Pending", "STRANGER": "Pending"}

    # No active listings this run; TRACKED went under contract.
    save_listings(csv_path, [], known, pending_map=pending_map)

    rows = _read(csv_path)
    assert rows["TRACKED"]["status"] == "Pending"
    assert "STRANGER" not in rows  # never imported


def test_active_status_overrides_pending(tmp_path: Path):
    csv_path = tmp_path / "listings.csv"
    known = _make_known("TRACKED")
    active = Listing(
        listing_id="TRACKED", address="1 Main St, Natick, MA", price=1000000,
        beds=3, baths=2, sqft=2000, url="http://x", town="Natick, MA",
        property_type="Single Family Residential", days_on_market=5,
        year_built=1990, status="Active",
    )
    pending_map = {"TRACKED": "Pending"}

    save_listings(csv_path, [active], known, pending_map=pending_map)

    rows = _read(csv_path)
    assert rows["TRACKED"]["status"] == "Active"  # back on market wins
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pending_merge.py -v`
Expected: FAIL — `assert 'status' in CSV_FIELDS` fails / `save_listings()` has no `pending_map` kwarg.

- [ ] **Step 3: Add `status` to `CSV_FIELDS`**

In `code/analyzer.py`, append `"status"` to the `CSV_FIELDS` list (add at the end, after `"station_minutes"`):

```python
    "station_minutes",
    "status",
```

- [ ] **Step 4: Set status on active listings + add pending merge**

In `code/analyzer.py`, change the `save_listings` signature:

```python
def save_listings(
    csv_path: Path,
    listings: list[Listing],
    known: dict[str, dict],
    pending_map: dict[str, str] | None = None,
) -> None:
```

In the **update branch** (`if lid in updated:`), add (alongside the other refreshed fields):

```python
            updated[lid]["status"] = listing.status or "Active"
```

In the **create branch** (`else:` dict literal), add a `"status"` key:

```python
                "status": listing.status or "Active",
```

Then, **after** the `for listing in listings:` loop and **before** `with open(csv_path, ...)`, add the known-only pending merge:

```python
    # Flag listings we are already tracking that have gone under contract.
    # Only touch ids already in `updated` (known or seen-active this run); never
    # import strangers' pending homes. Active status set above always wins, so
    # skip ids that appeared in this run's active `listings`.
    if pending_map:
        active_ids = {l.listing_id for l in listings}
        for lid, label in pending_map.items():
            if lid in updated and lid not in active_ids:
                updated[lid]["status"] = label
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_pending_merge.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Run the full suite**

Run: `python -m pytest -v`
Expected: all green (Tasks 1, 2, 4 tests pass)

- [ ] **Step 7: Commit**

```bash
git add code/analyzer.py tests/test_pending_merge.py
git commit -m "Persist listing status + flag known listings that went pending"
```

---

## Task 5: Refactor html_writer to expose render_page() -> str

This is a pure refactor: `write_html` keeps its behavior but delegates string
construction to a new `render_page` that the Flask app can call directly.

**Files:**
- Modify: `code/html_writer.py` (`write_html` ~line 394)
- Create: `tests/test_render_page.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_render_page.py`:

```python
import csv
from pathlib import Path

from code.html_writer import render_page, CSV_FIELDS_HINT  # noqa


def _write_csv(path: Path, rows: list[dict]):
    fields = list(rows[0].keys())
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def _row(**kw) -> dict:
    base = {
        "listing_id": "73000001", "address": "1 Main St, Natick, MA",
        "price": "1000000", "beds": "3", "baths": "2", "sqft": "2000",
        "url": "https://redfin.com/x", "town": "Natick, MA",
        "property_type": "Single Family Residential", "days_on_market": "5",
        "year_built": "1990", "first_seen": "2026-06-01",
        "last_seen": "2026-06-07", "last_price": "1000000", "remarks": "",
        "builder_owned": "", "builder_match": "", "latitude": "", "longitude": "",
        "nearest_station": "", "station_miles": "", "station_minutes": "",
        "status": "Active",
    }
    base.update(kw)
    return base


def test_render_page_returns_html_string(tmp_path: Path):
    csv_path = tmp_path / "listings.csv"
    _write_csv(csv_path, [_row()])
    html = render_page(csv_path, {"Natick, MA": 12.10}, 900000, 1500000)
    assert html.startswith("<!DOCTYPE html>")
    assert "1 Main St" in html
```

Note: `CSV_FIELDS_HINT` does not need to exist — remove that import line; it is
a leftover. Use exactly:

```python
from code.html_writer import render_page
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_render_page.py -v`
Expected: FAIL — `ImportError: cannot import name 'render_page'`

- [ ] **Step 3: Extract `render_page`**

In `code/html_writer.py`, rename the current `write_html` body. Concretely:

1. Add a new function `render_page` with this signature, containing **everything
   currently in `write_html` from its first line down to the assignment of the
   `html` variable** (i.e. all the body/section building and the final
   `html = f"""..."""` block), then `return html`:

```python
def render_page(
    csv_path: Path,
    tax_rates: dict[str, float] | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    annotations: dict[str, dict] | None = None,
    interactive: bool = False,
) -> str:
    tax_rates = tax_rates or {}
    annotations = annotations or {}
    if not csv_path.exists():
        return ""
    # ... (all existing body/section-building code, unchanged for now) ...
    # ... existing `html = f"""<!DOCTYPE html> ... """` ...
    return html
```

2. Replace `write_html` with a thin wrapper that keeps the file/asset writes:

```python
def write_html(
    csv_path: Path,
    html_path: Path,
    tax_rates: dict[str, float] | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    annotations: dict[str, dict] | None = None,
    interactive: bool = False,
) -> None:
    html = render_page(
        csv_path, tax_rates, min_price, max_price,
        annotations=annotations, interactive=interactive,
    )
    if not html:
        return
    html_path.parent.mkdir(parents=True, exist_ok=True)
    asset_src = Path(__file__).resolve().parent.parent / "site" / "chalkboard.jpg"
    asset_dst = html_path.parent / "chalkboard.jpg"
    if asset_src.exists() and asset_src.resolve() != asset_dst.resolve():
        shutil.copyfile(asset_src, asset_dst)
    html_path.write_text(html)
```

(Move the `html_path.parent.mkdir(...)`, asset copy, and `html_path.write_text`
lines OUT of `render_page` and into `write_html`. `render_page` must not touch
the filesystem except reading `csv_path`.)

- [ ] **Step 4: Thread annotations + interactive into card calls**

Inside `render_page`, the two places that call `_render_card(...)` must pass the
annotation and interactive flag. Update both call sites:

The "new" section call becomes:
```python
            cards = "".join(
                _render_card(r, rate, is_recent=True,
                             annotation=annotations.get(r.get("listing_id", "")),
                             interactive=interactive)
                for r in town_new
            )
```
The per-town section call becomes:
```python
        cards = "".join(
            _render_card(r, rate, is_recent=_is_new(r, cutoff),
                         annotation=annotations.get(r.get("listing_id", "")),
                         interactive=interactive)
            for r in listings
        )
```

(`_render_card` gains these params in Task 6; until then it ignores them — so
add the params in Task 6 Step 3 before running Task 5's test. To keep TDD order
clean, run Task 5 Step 5 only after Task 6 Step 3. Simplest: do Task 5 Steps 3–4,
then Task 6 fully, then run both test files together.)

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_render_page.py -v` (after Task 6 Step 3)
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add code/html_writer.py tests/test_render_page.py
git commit -m "Extract render_page() string builder from write_html"
```

---

## Task 6: Render annotation controls + read-only annotations on cards

**Files:**
- Modify: `code/html_writer.py` (`_render_card` ~line 297; add label-slug helper)
- Create: `tests/test_card_annotations.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_card_annotations.py`:

```python
from code.html_writer import _render_card

ROW = {
    "listing_id": "73000001", "address": "1 Main St, Natick, MA",
    "price": "1000000", "beds": "3", "baths": "2", "sqft": "2000",
    "url": "https://redfin.com/x", "town": "Natick, MA",
    "property_type": "Single Family Residential", "days_on_market": "5",
    "year_built": "1990", "first_seen": "2026-06-01", "last_price": "1000000",
    "remarks": "", "builder_owned": "", "builder_match": "",
    "nearest_station": "", "station_miles": "", "station_minutes": "",
    "status": "Active",
}


def test_card_has_listing_id():
    html = _render_card(ROW, 0.0)
    assert 'data-listing-id="73000001"' in html


def test_interactive_card_has_select_and_textarea():
    html = _render_card(ROW, 0.0, interactive=True)
    assert 'class="annotate-status"' in html
    assert 'class="annotate-note"' in html
    assert "Worth visiting" in html  # option present


def test_readonly_card_shows_annotation_without_controls():
    ann = {"status_label": "Favorite", "note": "best so far"}
    html = _render_card(ROW, 0.0, annotation=ann, interactive=False)
    assert "best so far" in html
    assert "Favorite" in html
    assert 'class="annotate-status"' not in html  # no editable control


def test_label_adds_css_class_for_filtering():
    ann = {"status_label": "Worth visiting", "note": ""}
    html = _render_card(ROW, 0.0, annotation=ann, interactive=True)
    assert "label-worth-visiting" in html
    assert 'data-label="Worth visiting"' in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_card_annotations.py -v`
Expected: FAIL — `_render_card()` got an unexpected keyword `interactive` / `data-listing-id` absent.

- [ ] **Step 3: Add label-slug helper + extend `_render_card`**

In `code/html_writer.py`, add near `_esc` (top of helpers):

```python
from code.annotations import STATUS_LABELS


def _label_slug(label: str) -> str:
    return label.lower().replace(" ", "-")
```

Change the `_render_card` signature:

```python
def _render_card(
    row: dict,
    tax_rate_per_1000: float,
    is_recent: bool = False,
    annotation: dict | None = None,
    interactive: bool = False,
) -> str:
```

Near the top of `_render_card` body add:

```python
    annotation = annotation or {}
    listing_id = (row.get("listing_id") or "").strip()
    label = (annotation.get("status_label") or "").strip()
    note = (annotation.get("note") or "").strip()
    status = (row.get("status") or "").strip()
    is_pending = status in ("Pending", "Contingent")
```

In the `badge_parts` block, after the builder-owned badge, add the pending badge:

```python
    if is_pending:
        badge_parts.append(f'<span class="badge pending-badge">Sale {status.lower()}</span>')
```

In the `class_parts` block (where `"price-drop"`, `"is-new"` are appended), add:

```python
    if label:
        class_parts.append(f"label-{_label_slug(label)}")
    if is_pending:
        class_parts.append("card-pending")
```

Build the annotation HTML block (place this just before the `return f"""...`):

```python
    if interactive:
        options = ['<option value="">— no label —</option>']
        for opt in STATUS_LABELS:
            sel = " selected" if opt == label else ""
            options.append(f'<option value="{_esc(opt)}"{sel}>{_esc(opt)}</option>')
        annotate_html = (
            '<div class="annotate">'
            f'<select class="annotate-status">{"".join(options)}</select>'
            f'<textarea class="annotate-note" rows="2" '
            f'placeholder="Notes…">{_esc(note)}</textarea>'
            '<span class="save-state" aria-hidden="true"></span>'
            '</div>'
        )
    else:
        chip = f'<span class="label-chip">{_esc(label)}</span>' if label else ""
        note_html = f'<div class="note-readonly">{_esc(note)}</div>' if note else ""
        annotate_html = (
            f'<div class="annotate readonly">{chip}{note_html}</div>'
            if (chip or note_html) else ""
        )
```

Finally, update the returned card markup: add `data-listing-id` and `data-label`
to the root div, and insert `{annotate_html}` just before the closing `</div>` of
the card. Replace the `return f"""..."""` block with:

```python
    return f"""
<div class="{card_class}" data-listing-id="{_esc(listing_id)}" data-label="{_esc(label)}">
  <div class="card-top">
    <div class="price">${price:,.0f}</div>
    {badges_html}
  </div>
  <div class="facts">{specs}</div>
  <div class="address"><a href="{_esc(url)}" target="_blank" rel="noopener noreferrer">{_esc(address)}</a></div>
  <div class="details">
    <div>Built: {_esc(year_built if year_built else "unknown")}</div>
    {tax_html}
    {transit_html}
    <div class="footer">{_esc(" · ".join(footer_parts))}</div>
  </div>
  {annotate_html}
</div>"""
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_card_annotations.py tests/test_render_page.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add code/html_writer.py tests/test_card_annotations.py
git commit -m "Render annotation controls (interactive) and read-only labels/notes on cards"
```

---

## Task 7: CSS + JS (label colors, pending dim, filter bar, autosave)

**Files:**
- Modify: `code/html_writer.py` (`_CSS` ~line 21; add filter bar + `<script>` in `render_page`)

No new unit test (visual/JS behavior is verified in the Task 11 smoke test). Keep
the JS dependency-free and bound only to elements that exist.

- [ ] **Step 1: Append CSS**

In `code/html_writer.py`, append to the `_CSS` string (before its closing `"""`):

```css
/* --- annotations --- */
.annotate { padding: 10px 14px 14px; border-top: 1px solid #e7e9e4; display: flex; flex-direction: column; gap: 6px; }
.annotate-status { font: inherit; padding: 4px 6px; border: 1px solid #cdd2c9; border-radius: 6px; background: #fff; }
.annotate-note { font: inherit; padding: 6px 8px; border: 1px solid #cdd2c9; border-radius: 6px; resize: vertical; }
.annotate.readonly { gap: 4px; }
.label-chip { align-self: flex-start; font-size: 12px; font-weight: 600; padding: 2px 8px; border-radius: 999px; background: #265d7e; color: #fff; }
.note-readonly { font-size: 13px; color: #4a4f48; white-space: pre-wrap; }
.save-state.saving::after { content: "saving…"; font-size: 11px; color: #888; }
.save-state.saved::after  { content: "saved";   font-size: 11px; color: #2e7d32; }
.save-state.failed::after { content: "save failed"; font-size: 11px; color: #c62828; }
/* label-colored left border */
.card.label-favorite          { border-left: 5px solid #c2185b; }
.card.label-worth-visiting    { border-left: 5px solid #2e7d32; }
.card.label-visited           { border-left: 5px solid #1565c0; }
.card.label-touring-scheduled { border-left: 5px solid #6a1b9a; }
.card.label-maybe             { border-left: 5px solid #f9a825; }
.card.label-rejected          { border-left: 5px solid #9e9e9e; }
/* sale pending */
.badge.pending-badge { background: #8d6e63; color: #fff; }
.card.card-pending { opacity: 0.55; filter: grayscale(0.35); }
/* filter bar */
.filter-bar { display: flex; align-items: center; gap: 8px; margin: 0 0 16px; }
.filter-bar select { font: inherit; padding: 4px 8px; border: 1px solid #cdd2c9; border-radius: 6px; }
```

- [ ] **Step 2: Add the filter bar into the content**

In `render_page`, find `<div class="content">` and change it to include a filter
bar above `{body}`. Build the options from `STATUS_LABELS` near where `body` is
assembled:

```python
    filter_options = '<option value="">All labels</option>' + "".join(
        f'<option value="{_esc(l)}">{_esc(l)}</option>' for l in STATUS_LABELS
    )
    filter_bar = (
        f'<div class="filter-bar"><label for="label-filter">Show:</label>'
        f'<select id="label-filter">{filter_options}</select></div>'
    )
```

Then in the big `html = f"""..."""`, replace:

```html
  <div class="content">
    {body}
  </div>
```
with:
```html
  <div class="content">
    {filter_bar}
    {body}
  </div>
```

- [ ] **Step 3: Add the script before `</body>`**

Define the script string near the top of `render_page` (it's static):

```python
    page_js = """
<script>
(function () {
  document.querySelectorAll('.card[data-listing-id]').forEach(function (card) {
    var id = card.getAttribute('data-listing-id');
    if (!id) return;
    var sel = card.querySelector('.annotate-status');
    var note = card.querySelector('.annotate-note');
    var state = card.querySelector('.save-state');
    function setLabelClass(v) {
      card.className = card.className.replace(/\\blabel-[\\w-]+/g, '').trim();
      card.setAttribute('data-label', v || '');
      if (v) card.classList.add('label-' + v.toLowerCase().replace(/ /g, '-'));
    }
    function save() {
      if (state) { state.className = 'save-state saving'; }
      fetch('/api/annotations/' + encodeURIComponent(id), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          status_label: sel ? sel.value : '',
          note: note ? note.value : ''
        })
      }).then(function (r) {
        if (!r.ok) throw new Error('bad status');
        if (sel) setLabelClass(sel.value);
        if (state) { state.className = 'save-state saved'; }
      }).catch(function () {
        if (state) { state.className = 'save-state failed'; }
      });
    }
    if (sel) sel.addEventListener('change', save);
    if (note) {
      var t;
      note.addEventListener('input', function () {
        clearTimeout(t); t = setTimeout(save, 800);
      });
    }
  });
  var filter = document.getElementById('label-filter');
  if (filter) {
    filter.addEventListener('change', function () {
      var v = filter.value;
      document.querySelectorAll('.card[data-listing-id]').forEach(function (card) {
        var sel = card.querySelector('.annotate-status');
        var lbl = sel ? sel.value : (card.getAttribute('data-label') || '');
        card.style.display = (!v || v === lbl) ? '' : 'none';
      });
    });
  }
})();
</script>
"""
```

Then in the `html = f"""..."""`, change `</body>` to:

```html
{page_js}
</body>
```

(The save handlers bind only to `.annotate-status` / `.annotate-note`, which exist
only when `interactive=True`. On the read-only mirror there are no controls, so
the POST code never runs; the filter still works. Safe to include unconditionally.)

- [ ] **Step 4: Verify the suite still passes**

Run: `python -m pytest -v`
Expected: all green (no test asserts on JS/CSS, but rendering must not break).

- [ ] **Step 5: Commit**

```bash
git add code/html_writer.py
git commit -m "Add annotation CSS, label filter bar, and autosave/filter JS"
```

---

## Task 8: Flask app (serve dashboard + annotations API)

**Files:**
- Create: `code/app.py`
- Create: `tests/test_app.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_app.py`:

```python
import csv
from pathlib import Path

from code.app import create_app


def _write_csv(path: Path):
    fields = [
        "listing_id", "address", "price", "beds", "baths", "sqft", "url",
        "town", "property_type", "days_on_market", "year_built", "first_seen",
        "last_seen", "last_price", "remarks", "builder_owned", "builder_match",
        "latitude", "longitude", "nearest_station", "station_miles",
        "station_minutes", "status",
    ]
    row = {f: "" for f in fields}
    row.update({
        "listing_id": "73000001", "address": "1 Main St, Natick, MA",
        "price": "1000000", "beds": "3", "baths": "2", "sqft": "2000",
        "url": "https://redfin.com/x", "town": "Natick, MA",
        "property_type": "Single Family Residential", "days_on_market": "5",
        "year_built": "1990", "first_seen": "2026-06-01",
        "last_seen": "2026-06-07", "last_price": "1000000", "status": "Active",
    })
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerow(row)


def _client(tmp_path: Path):
    csv_path = tmp_path / "listings.csv"
    db_path = tmp_path / "annotations.db"
    _write_csv(csv_path)
    app = create_app(csv_path, db_path, {"Natick, MA": 12.10}, 900000, 1500000)
    app.config.update(TESTING=True)
    return app.test_client()


def test_index_serves_dashboard(tmp_path: Path):
    c = _client(tmp_path)
    r = c.get("/")
    assert r.status_code == 200
    assert b"1 Main St" in r.data
    assert b"annotate-status" in r.data  # interactive controls present


def test_annotations_roundtrip(tmp_path: Path):
    c = _client(tmp_path)
    assert c.get("/api/annotations").get_json() == {}
    r = c.post("/api/annotations/73000001",
               json={"status_label": "Worth visiting", "note": "nice"})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    got = c.get("/api/annotations").get_json()
    assert got["73000001"]["status_label"] == "Worth visiting"
    assert got["73000001"]["note"] == "nice"


def test_rejects_invalid_label(tmp_path: Path):
    c = _client(tmp_path)
    r = c.post("/api/annotations/73000001",
               json={"status_label": "Bogus", "note": ""})
    assert r.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_app.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'code.app'`

- [ ] **Step 3: Implement `code/app.py`**

```python
"""Always-on Flask app: serves the interactive dashboard on the home LAN and
accepts annotation edits. Run via `python -m code.app` (see
house-bot-dashboard.service). Reads data/listings.csv (written nightly by the
bot) and reads/writes data/annotations.db.
"""
from pathlib import Path

import yaml
from flask import Flask, Response, jsonify, request

from code import annotations as ann
from code.html_writer import render_page

BASE_DIR = Path(__file__).resolve().parent.parent


def create_app(csv_path, db_path, tax_rates=None, min_price=None, max_price=None):
    app = Flask(__name__)
    csv_path, db_path = Path(csv_path), Path(db_path)
    ann.init_db(db_path)

    @app.get("/")
    def index():
        html = render_page(
            csv_path, tax_rates or {}, min_price, max_price,
            annotations=ann.get_all(db_path), interactive=True,
        )
        return Response(html or "<p>No listings yet.</p>", mimetype="text/html")

    @app.get("/api/annotations")
    def list_annotations():
        return jsonify(ann.get_all(db_path))

    @app.post("/api/annotations/<listing_id>")
    def set_annotation(listing_id):
        data = request.get_json(silent=True) or {}
        label = (data.get("status_label") or "").strip()
        note = (data.get("note") or "").strip()
        if label and label not in ann.STATUS_LABELS:
            return jsonify({"error": "invalid label"}), 400
        ann.upsert(db_path, listing_id, label, note)
        return jsonify({"ok": True})

    return app


def main():
    config = yaml.safe_load((BASE_DIR / "config" / "searches.yaml").read_text())
    tax_rates = {
        t["name"]: float(t.get("tax_rate_per_1000") or 0)
        for t in config.get("towns", [])
    }
    search_cfg = config.get("search", {})
    app = create_app(
        BASE_DIR / "data" / "listings.csv",
        BASE_DIR / "data" / "annotations.db",
        tax_rates,
        search_cfg.get("min_price"),
        search_cfg.get("max_price"),
    )
    port = int(config.get("dashboard", {}).get("port", 8000))
    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_app.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add code/app.py tests/test_app.py
git commit -m "Add Flask app serving interactive dashboard + annotations API"
```

---

## Task 9: Wire pending fetch + mirror annotation scope into main.py

**Files:**
- Modify: `main.py`
- Modify: `config/searches.yaml`

- [ ] **Step 1: Add config knobs**

In `config/searches.yaml`, add a top-level block (e.g. after the `search:` block):

```yaml
# ── Local dashboard app ────────────────────────────────────────────────────
dashboard:
  port: 8000              # http://<this-desktop>:8000 on your home WiFi

# What the bot bakes into the PUBLIC GitHub Pages mirror:
#   full   = status labels + notes  (NOTE: the gh-pages repo is world-readable)
#   labels = status labels only (notes stay local)
#   none   = no annotations on the public copy
mirror_annotations: full
```

- [ ] **Step 2: Import and fetch pending in `main.py`**

In `main.py`, update the import line:

```python
from code.searcher import enrich_remarks, search_all, fetch_pending_map
```

and add:

```python
from code import annotations as ann
```

After `listings = search_all(config)` and its print, add:

```python
    print("Checking for under-contract (pending) listings...")
    pending_map = fetch_pending_map(config)
    print(f"Pending/contingent in criteria: {len(pending_map)}")
```

- [ ] **Step 3: Pass pending_map to save_listings**

Change:
```python
    save_listings(LISTINGS_CSV, listings, known)
```
to:
```python
    save_listings(LISTINGS_CSV, listings, known, pending_map=pending_map)
```

- [ ] **Step 4: Bake annotations (scoped) into the mirror render**

Replace the `write_html(...)` call in `main.py` with:

```python
    db_path = BASE_DIR / "data" / "annotations.db"
    mirror_scope = config.get("mirror_annotations", "full")
    mirror_anns = ann.get_all(db_path)
    if mirror_scope == "none":
        mirror_anns = {}
    elif mirror_scope == "labels":
        mirror_anns = {k: {**v, "note": ""} for k, v in mirror_anns.items()}

    html_path = BASE_DIR / "output" / "listings.html"
    search_cfg = config.get("search", {})
    write_html(
        LISTINGS_CSV, html_path, tax_rates,
        min_price=search_cfg.get("min_price"),
        max_price=search_cfg.get("max_price"),
        annotations=mirror_anns,
        interactive=False,
    )
    print(f"Listings: {html_path}")
```

(Remove the now-duplicated original `html_path = ...` / `write_html(...)` /
`print(...)` lines so they appear only once.)

- [ ] **Step 5: Verify main.py imports cleanly**

Run: `python -c "import ast,sys; ast.parse(open('main.py').read()); print('ok')"`
Expected: `ok`

- [ ] **Step 6: Run full suite**

Run: `python -m pytest -v`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add main.py config/searches.yaml
git commit -m "Wire pending detection + scoped annotation baking into nightly run"
```

---

## Task 10: systemd service, gitignore, requirements

**Files:**
- Create: `house-bot-dashboard.service`
- Modify: `.gitignore`, `requirements.txt`

- [ ] **Step 1: Create the service unit**

Create `house-bot-dashboard.service`:

```ini
[Unit]
Description=House search interactive dashboard (Flask)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=%h/projects/claude/house-bot
ExecStart=%h/projects/claude/house-bot/.venv/bin/python -m code.app
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
```

- [ ] **Step 2: Ignore the annotations DB explicitly**

`data/` is already gitignored, but `annotations.db` is created at runtime and
must never be committed. Add to `.gitignore` (explicit, in case `data/` is ever
un-ignored):

```
data/annotations.db
```

- [ ] **Step 3: Finalize requirements.txt**

Ensure `requirements.txt` reads exactly:

```
requests
curl_cffi
pyyaml
python-dotenv
flask
pytest
```

- [ ] **Step 4: Commit**

```bash
git add house-bot-dashboard.service .gitignore requirements.txt
git commit -m "Add dashboard systemd service; ignore annotations.db; add flask/pytest"
```

---

## Task 11: Manual smoke test + docs

**Files:**
- Modify: `CLAUDE.md`, `README.md`

- [ ] **Step 1: Start the app against current data**

```bash
cd ~/projects/claude/house-bot && source .venv/bin/activate
python -m code.app &
sleep 2
curl -s http://localhost:8000/ | grep -o 'annotate-status' | head -1
```
Expected: prints `annotate-status` (controls rendered). If `data/listings.csv`
doesn't exist yet, run `python main.py` once first.

- [ ] **Step 2: Exercise the API**

```bash
curl -s -X POST http://localhost:8000/api/annotations/TESTID \
  -H 'Content-Type: application/json' \
  -d '{"status_label":"Worth visiting","note":"smoke test"}'
curl -s http://localhost:8000/api/annotations
```
Expected: first returns `{"ok":true}`; second shows `TESTID` with the note.
Then stop the app: `kill %1`. (The `TESTID` row is harmless; it just won't match
any card. Optionally delete it: `sqlite3 data/annotations.db "DELETE FROM annotations WHERE listing_id='TESTID';"`)

- [ ] **Step 3: Open in a browser on the LAN**

From your phone/wife's laptop on the same WiFi, open `http://<desktop-ip>:8000`,
pick a label on a card, type a note, reload — confirm it persists and the card
border colors. Confirm the "Show:" filter hides non-matching cards.

- [ ] **Step 4: Enable the service**

```bash
cp house-bot-dashboard.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now house-bot-dashboard.service
systemctl --user status house-bot-dashboard.service --no-pager | head -5
```
Expected: `active (running)`.

- [ ] **Step 5: Update docs**

In `README.md` and `CLAUDE.md`, add an "Interactive dashboard" section covering:
- The app runs at `http://<desktop>:<dashboard.port>` on the home LAN (no auth).
- Status labels (the six) + free-text notes, stored in `data/annotations.db`
  (SQLite, gitignored, **not** pushed).
- Sale-pending: a second Redfin query (`status=130`); only **already-tracked**
  listings that go under contract are flagged (badge + dimmed `card-pending`);
  fall-throughs auto-revert when they reappear as Active.
- The public GitHub Pages mirror is read-only and bakes annotations per
  `mirror_annotations` (`full`/`labels`/`none`) — **`full` publishes notes
  publicly** since the gh-pages repo is world-readable.
- Two systemd units: `house-bot.timer` (nightly fetch) and
  `house-bot-dashboard.service` (always-on app).

- [ ] **Step 6: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "Document interactive dashboard, annotations, and sale-pending"
```

---

## Self-Review (completed during planning)

- **Spec coverage:** annotations store (T1), status parse (T2), pending fetch
  (T3), known-only pending merge + persistence (T4), render refactor (T5),
  card controls/read-only (T6), CSS/JS/filter (T7), Flask API (T8), nightly
  wiring + mirror scope (T9), service/ignore/deps (T10), docs/smoke (T11). All
  spec sections mapped.
- **Type consistency:** `STATUS_LABELS` defined once in `code/annotations.py`,
  imported by `app.py` and `html_writer.py`. `render_page`/`write_html`/
  `_render_card` share the `annotations`/`interactive` params. `save_listings`
  gains `pending_map` used consistently in T4 and T9. CSV `status` column added
  in T4 and read in T6, written by T4, served by T8.
- **Placeholders:** none — every code step has complete code.
- **Ordering caveat (noted in T5/T6):** add `_render_card`'s new params (T6 Step
  3) before running T5's render_page test; run T5+T6 tests together.
