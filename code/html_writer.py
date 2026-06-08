import csv
import html
import re
import shutil
from datetime import date, timedelta
from pathlib import Path

from code.annotations import STATUS_LABELS


def _label_slug(label: str) -> str:
    return re.sub(r"[^a-z0-9-]", "", label.lower().replace(" ", "-"))

# How far back a listing's first_seen can be and still appear in the top
# "New" section. Rolling window so the section stays useful even if a daily
# run is missed; per-town sections below always show everything.
NEW_WINDOW_DAYS = 7


def _fmt_price_compact(price: float) -> str:
    """900000 -> '$900K', 1500000 -> '$1.5M' (for the header label)."""
    if price >= 1_000_000:
        millions = price / 1_000_000
        return f"${millions:.1f}M".replace(".0M", "M")
    return f"${price / 1000:.0f}K"


_CSS = """
:root {
  --ink: #1f2428;
  --muted: #68727d;
  --line: #dfe5df;
  --paper: #fbfaf6;
  --surface: #ffffff;
  --soft: #eef3ef;
  --green: #2d6a4f;
  --green-dark: #163d31;
  --blue: #265d7e;
  --copper: #b95e3e;
  --gold: #9c6b1e;
  --shadow: 0 12px 34px rgba(31, 36, 40, 0.08);
}
* { box-sizing: border-box; margin: 0; padding: 0; }
html { background: var(--paper); }
body {
  min-width: 320px;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: linear-gradient(180deg, #f3f6f0 0%, var(--paper) 22rem);
  color: var(--ink);
  line-height: 1.45;
}
a { color: inherit; }
.page {
  width: min(1180px, calc(100% - 32px));
  margin: 0 auto;
  padding: 24px 0 48px;
}
.hero {
  position: relative;
  overflow: hidden;
  border-radius: 8px;
  color: #fff;
  background:
    linear-gradient(90deg, rgba(18, 45, 37, 0.94), rgba(18, 45, 37, 0.80) 48%, rgba(18, 45, 37, 0.55)),
    url("chalkboard.jpg") center / cover;
  box-shadow: var(--shadow);
}
.hero::after {
  content: "";
  position: absolute;
  inset: 0;
  pointer-events: none;
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: inherit;
}
.hero-content { position: relative; z-index: 1; padding: 28px; }
.eyebrow {
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: #b8dfc7;
  margin-bottom: 6px;
}
.hero-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
}
h1 {
  font-size: clamp(1.85rem, 4vw, 3rem);
  line-height: 1.05;
  font-weight: 750;
  letter-spacing: 0;
}
.updated-pill {
  flex: 0 0 auto;
  border: 1px solid rgba(255,255,255,0.28);
  background: rgba(255,255,255,0.13);
  border-radius: 999px;
  padding: 7px 11px;
  font-size: 0.78rem;
  font-weight: 650;
  color: #eef8f0;
}
.hero-copy {
  max-width: 720px;
  margin-top: 10px;
  color: rgba(255,255,255,0.82);
  font-size: 0.98rem;
}
.nowrap { white-space: nowrap; }
.stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-top: 22px;
}
.stat {
  min-height: 78px;
  border-radius: 8px;
  background: rgba(255,255,255,0.94);
  color: var(--ink);
  padding: 12px 14px;
  box-shadow: 0 8px 20px rgba(0,0,0,0.14);
}
.stat-label {
  display: block;
  color: var(--muted);
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.stat-value {
  display: block;
  margin-top: 4px;
  color: var(--green-dark);
  font-size: 1.35rem;
  font-weight: 780;
}
.content { margin-top: 24px; }
.section {
  margin-top: 28px;
  padding-top: 2px;
}
.section:first-child { margin-top: 0; }
.section-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 12px;
  border-bottom: 1px solid var(--line);
  padding-bottom: 9px;
}
h2 {
  color: var(--green-dark);
  font-size: 1rem;
  font-weight: 780;
  letter-spacing: 0;
}
.section-count {
  color: var(--muted);
  font-size: 0.78rem;
  font-weight: 650;
}
.town-block { margin-top: 18px; }
.town-heading {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #4d5962;
  font-size: 0.85rem;
  font-weight: 760;
  margin: 0 0 8px;
}
.town-heading::before {
  content: "";
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--blue);
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(290px, 1fr));
  gap: 14px;
}
.card {
  display: flex;
  min-height: 178px;
  flex-direction: column;
  gap: 10px;
  background: var(--surface);
  border: 1px solid rgba(31, 36, 40, 0.09);
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 3px 12px rgba(31, 36, 40, 0.05);
  transition: transform 150ms ease, box-shadow 150ms ease, border-color 150ms ease;
}
.card:hover {
  transform: translateY(-2px);
  border-color: rgba(45, 106, 79, 0.28);
  box-shadow: 0 14px 26px rgba(31, 36, 40, 0.09);
}
.card.price-drop { border-left: 4px solid var(--copper); }
.card.is-new { border-top: 3px solid var(--blue); }
.card-top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}
.price {
  color: var(--ink);
  font-size: 1.38rem;
  font-weight: 800;
  line-height: 1.05;
}
.badges {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: flex-end;
}
.badge {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  border-radius: 999px;
  padding: 3px 8px;
  font-size: 0.7rem;
  font-weight: 750;
  white-space: nowrap;
}
.drop-badge { background: #f7e1d9; color: #8f3f29; }
.new-build { background: #dff0e5; color: #1f5e43; }
.builder-own { background: #f8edc9; color: #795111; }
.builder-own[title] { cursor: help; }
.facts {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  color: #43505a;
  font-size: 0.86rem;
}
.fact {
  border: 1px solid #e3e8e3;
  border-radius: 999px;
  background: #f7f9f6;
  padding: 3px 8px;
}
.address a {
  display: inline-block;
  color: var(--blue);
  font-size: 0.94rem;
  font-weight: 720;
  text-decoration: none;
  overflow-wrap: anywhere;
}
.address a:hover { text-decoration: underline; }
.details {
  display: grid;
  gap: 4px;
  margin-top: auto;
  color: var(--muted);
  font-size: 0.8rem;
}
.tax { color: #3f4c45; font-size: 0.82rem; }
.tax-rate { color: var(--muted); }
.transit { color: var(--blue); font-size: 0.82rem; }
.transit .station { font-weight: 650; }
.footer { color: #7b858c; }
.none {
  border: 1px dashed var(--line);
  border-radius: 8px;
  background: rgba(255,255,255,0.62);
  color: var(--muted);
  padding: 18px;
  font-style: italic;
}
@media (max-width: 760px) {
  .page { width: min(100% - 20px, 1180px); padding-top: 10px; }
  .hero-content { padding: 20px; }
  .hero-top { display: block; }
  .updated-pill { display: inline-flex; margin-top: 12px; }
  .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .grid { grid-template-columns: 1fr; }
  .section-header { align-items: flex-start; flex-direction: column; gap: 3px; }
}
@media (max-width: 430px) {
  .card-top { display: block; }
  .badges { justify-content: flex-start; margin-top: 8px; }
}
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
"""


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _render_card(
    row: dict,
    tax_rate_per_1000: float,
    is_recent: bool = False,
    annotation: dict | None = None,
    interactive: bool = False,
) -> str:
    annotation = annotation or {}
    listing_id = (row.get("listing_id") or "").strip()
    label = (annotation.get("status_label") or "").strip()
    note = (annotation.get("note") or "").strip()
    status = (row.get("status") or "").strip()
    is_pending = status in ("Pending", "Contingent")

    price = float(row["price"])
    last_price = float(row.get("last_price") or row["price"])
    is_drop = price < last_price
    yr_str = (row.get("year_built") or "").strip()
    year_built = int(yr_str) if yr_str.isdigit() else None
    is_new_build = year_built is not None and year_built >= 2010

    beds = float(row.get("beds") or 0)
    baths = float(row.get("baths") or 0)
    sqft = float(row.get("sqft") or 0)
    dom = int(float(row.get("days_on_market") or 0))

    specs_parts = [f"{beds:.0f} bd", f"{baths:.1f} ba"]
    if sqft:
        specs_parts.append(f"{sqft:,.0f} sqft")
    specs = "".join(f'<span class="fact">{_esc(part)}</span>' for part in specs_parts)

    badge_parts = []
    if is_drop:
        pct = (last_price - price) / last_price * 100
        badge_parts.append(f'<span class="badge drop-badge">{pct:.1f}% drop</span>')
    if is_new_build:
        badge_parts.append('<span class="badge new-build">New build</span>')

    if (row.get("builder_owned") or "").strip() == "1":
        match = (row.get("builder_match") or "").strip()
        title_attr = f' title="Matched: {_esc(match)}"' if match else ""
        badge_parts.append(f'<span class="badge builder-own"{title_attr}>Builder-owned</span>')
    if is_pending:
        badge_parts.append(f'<span class="badge pending-badge">Sale {status.lower()}</span>')
    badges_html = f'<div class="badges">{"".join(badge_parts)}</div>' if badge_parts else ""

    url = row.get("url", "")
    address = row.get("address", "Unknown address")
    prop_type = row.get("property_type", "")
    first_seen = row.get("first_seen", "")

    footer_parts = []
    if dom:
        footer_parts.append(f"{dom}d on market")
    if prop_type:
        footer_parts.append(prop_type)
    if first_seen:
        footer_parts.append(f"first seen {first_seen}")

    annual_tax = price * tax_rate_per_1000 / 1000.0
    tax_html = (
        f'<div class="tax">Est. tax/yr: ${annual_tax:,.0f}'
        f' <span class="tax-rate">(@ ${tax_rate_per_1000:.2f}/$1000)</span></div>'
        if tax_rate_per_1000 > 0 else ""
    )

    # Driving distance to the nearest MBTA commuter rail station (cached in CSV).
    transit_html = ""
    station = (row.get("nearest_station") or "").strip()
    miles_str = (row.get("station_miles") or "").strip()
    if station and miles_str:
        minutes_str = (row.get("station_minutes") or "").strip()
        drive = f"{float(miles_str):.1f} mi"
        if minutes_str:
            drive += f" · {float(minutes_str):.0f} min"
        transit_html = (
            f'<div class="transit">🚆 {drive} by car to '
            f'<span class="station">{_esc(station)}</span></div>'
        )

    class_parts = ["card"]
    if is_drop:
        class_parts.append("price-drop")
    if is_recent:
        class_parts.append("is-new")
    if label:
        class_parts.append(f"label-{_label_slug(label)}")
    if is_pending:
        class_parts.append("card-pending")
    card_class = " ".join(class_parts)

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


def _is_new(row: dict, cutoff: date) -> bool:
    """True if the listing was first seen on or after `cutoff`."""
    raw = (row.get("first_seen") or "").strip()
    try:
        return date.fromisoformat(raw) >= cutoff
    except ValueError:
        return False


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
      document.querySelectorAll('.card[data-listing-id="' + id + '"]').forEach(function (c) {
        c.className = c.className.replace(/\\blabel-[\\w-]+/g, '').replace(/\\s+/g, ' ').trim();
        c.setAttribute('data-label', v || '');
        if (v) c.classList.add('label-' + v.toLowerCase().replace(/ /g, '-'));
      });
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
    if not csv_path.exists():
        return ""

    by_town: dict[str, list[dict]] = {}
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            by_town.setdefault(row["town"], []).append(row)

    total = sum(len(v) for v in by_town.values())
    today = date.today()
    all_rows = [row for rows in by_town.values() for row in rows]
    price_drop_total = sum(
        1 for row in all_rows
        if float(row.get("price") or 0) < float(row.get("last_price") or row.get("price") or 0)
    )
    new_build_total = sum(
        1 for row in all_rows
        if (row.get("year_built") or "").strip().isdigit()
        and int((row.get("year_built") or "").strip()) >= 2010
    )

    sections = []

    # Front section: listings first seen within the rolling window, grouped by
    # town (same order as the full sections below), newest-first within each
    # town. Cards are intentionally duplicated below in their town section —
    # this is a "what's new" summary, not a separate list.
    cutoff = today - timedelta(days=NEW_WINDOW_DAYS)
    new_by_town = {
        town: sorted(
            (r for r in rows if _is_new(r, cutoff)),
            key=lambda r: (r.get("first_seen") or "", -float(r.get("price") or 0)),
            reverse=True,
        )
        for town, rows in by_town.items()
    }
    new_total = sum(len(v) for v in new_by_town.values())
    if new_total:
        blocks = [
            '<section class="section section-new">',
            '<div class="section-header">',
            f"<h2>New in the last {NEW_WINDOW_DAYS} days</h2>",
            f'<span class="section-count">{new_total} listings</span>',
            "</div>",
        ]
        for town in sorted(new_by_town):
            town_new = new_by_town[town]
            if not town_new:
                continue
            rate = tax_rates.get(town, 0.0)
            cards = "".join(
                _render_card(r, rate, is_recent=True,
                             annotation=annotations.get(r.get("listing_id", "")),
                             interactive=interactive)
                for r in town_new
            )
            blocks.append(
                f'<div class="town-block"><h3 class="town-heading">{_esc(town)} ({len(town_new)})</h3>'
                f'<div class="grid">{cards}</div></div>'
            )
        blocks.append("</section>")
        sections.append("".join(blocks))

    for town in sorted(by_town):
        listings = sorted(by_town[town], key=lambda r: int(float(r["days_on_market"] or 0)))
        rate = tax_rates.get(town, 0.0)
        cards = "".join(
            _render_card(r, rate, is_recent=_is_new(r, cutoff),
                         annotation=annotations.get(r.get("listing_id", "")),
                         interactive=interactive)
            for r in listings
        )
        sections.append(
            '<section class="section">'
            '<div class="section-header">'
            f"<h2>{_esc(town)}</h2>"
            f'<span class="section-count">{len(listings)} listings</span>'
            "</div>"
            f'<div class="grid">{cards}</div>'
            "</section>"
        )

    body = "\n".join(sections) if sections else "<p class='none'>No listings yet.</p>"

    filter_options = '<option value="">All labels</option>' + "".join(
        f'<option value="{_esc(l)}">{_esc(l)}</option>' for l in STATUS_LABELS
    )
    filter_bar = (
        f'<div class="filter-bar"><label for="label-filter">Show:</label>'
        f'<select id="label-filter">{filter_options}</select></div>'
    )

    price_label = ""
    if min_price is not None and max_price is not None:
        price_label = f"{_fmt_price_compact(min_price)}&ndash;{_fmt_price_compact(max_price)}"

    towns_label = f"{len(by_town)} towns" if len(by_town) != 1 else "1 town"
    search_label = f'<span class="nowrap">{price_label}</span> · 3+ bd · 2+ ba' if price_label else "3+ bd · 2+ ba"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>House Search</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='6' fill='%23163d31'/%3E%3Cpath d='M6 16 16 7l10 9v10H9V16Z' fill='%23f7f9f6'/%3E%3Cpath d='M13 26v-7h6v7' fill='%23265d7e'/%3E%3C/svg%3E">
<style>{_CSS}</style>
</head>
<body>
<main class="page">
  <header class="hero">
    <div class="hero-content">
      <p class="eyebrow">Home shortlist</p>
      <div class="hero-top">
        <div>
          <h1>House Search</h1>
          <p class="hero-copy">{total} active listings across {towns_label}. {search_label}.</p>
        </div>
        <div class="updated-pill">Updated {today}</div>
      </div>
      <div class="stats">
        <div class="stat"><span class="stat-label">Listings</span><span class="stat-value">{total}</span></div>
        <div class="stat"><span class="stat-label">New this week</span><span class="stat-value">{new_total}</span></div>
        <div class="stat"><span class="stat-label">Price drops</span><span class="stat-value">{price_drop_total}</span></div>
        <div class="stat"><span class="stat-label">Built 2010+</span><span class="stat-value">{new_build_total}</span></div>
      </div>
    </div>
  </header>
  <div class="content">
    {filter_bar}
    {body}
  </div>
</main>
{page_js}
</body>
</html>"""

    return html


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
