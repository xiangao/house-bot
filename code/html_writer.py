import csv
from datetime import date
from pathlib import Path


_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
       background: #f5f5f5; color: #222; padding: 24px; }
h1 { font-size: 1.3rem; font-weight: 600; margin-bottom: 4px; }
.meta { font-size: 0.85rem; color: #666; margin-bottom: 24px; }
h2 { font-size: 1rem; font-weight: 600; color: #555; margin: 28px 0 10px;
     text-transform: uppercase; letter-spacing: 0.05em; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
.card { background: #fff; border-radius: 8px; padding: 16px;
        box-shadow: 0 1px 3px rgba(0,0,0,.08); }
.card.price-drop { border-left: 3px solid #e05c2b; }
.price { font-size: 1.25rem; font-weight: 700; color: #111; }
.drop-badge { font-size: 0.75rem; background: #fde8e0; color: #b84a1e;
              border-radius: 4px; padding: 2px 6px; margin-left: 8px;
              vertical-align: middle; }
.specs { font-size: 0.85rem; color: #555; margin: 4px 0 8px; }
.address a { font-size: 0.9rem; color: #1a73e8; text-decoration: none; font-weight: 500; }
.address a:hover { text-decoration: underline; }
.footer { font-size: 0.78rem; color: #999; margin-top: 8px; }
.none { color: #888; font-style: italic; margin-top: 8px; }
.new-build { font-size: 0.75rem; background: #e6f4ea; color: #1e7e34;
             border-radius: 4px; padding: 2px 6px; margin-left: 6px;
             vertical-align: middle; }
.year { font-size: 0.78rem; color: #888; margin-top: 4px; }
.tax { font-size: 0.85rem; color: #444; margin-top: 4px; }
.tax-rate { font-size: 0.75rem; color: #999; }
"""


def _render_card(row: dict, tax_rate_per_1000: float) -> str:
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

    specs_parts = [f"{beds:.0f} bd / {baths:.1f} ba"]
    if sqft:
        specs_parts.append(f"{sqft:,.0f} sqft")
    specs = "  ·  ".join(specs_parts)

    new_build_html = '<span class="new-build">New build</span>' if is_new_build else ""
    drop_html = ""
    if is_drop:
        pct = (last_price - price) / last_price * 100
        drop_html = f'<span class="drop-badge">▼ {pct:.1f}% drop</span>'

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

    card_class = "card price-drop" if is_drop else "card"
    return f"""
<div class="{card_class}">
  <div class="price">${price:,.0f}{drop_html}{new_build_html}</div>
  <div class="specs">{specs}</div>
  <div class="address"><a href="{url}" target="_blank">{address}</a></div>
  <div class="year">Built: {year_built if year_built else "unknown"}</div>
  {tax_html}
  <div class="footer">{" · ".join(footer_parts)}</div>
</div>"""


def write_html(csv_path: Path, html_path: Path, tax_rates: dict[str, float] | None = None) -> None:
    tax_rates = tax_rates or {}
    if not csv_path.exists():
        return

    by_town: dict[str, list[dict]] = {}
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            by_town.setdefault(row["town"], []).append(row)

    total = sum(len(v) for v in by_town.values())
    today = str(date.today())

    sections = []
    for town in sorted(by_town):
        listings = sorted(by_town[town], key=lambda r: int(float(r["days_on_market"] or 0)))
        rate = tax_rates.get(town, 0.0)
        cards = "".join(_render_card(r, rate) for r in listings)
        sections.append(f"<h2>{town} ({len(listings)})</h2><div class='grid'>{cards}</div>")

    body = "\n".join(sections) if sections else "<p class='none'>No listings yet.</p>"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>House Search</title>
<style>{_CSS}</style>
</head>
<body>
<h1>House Search</h1>
<p class="meta">{total} listings · $800K–$1.2M · 3+ bd · 2+ ba · updated {today}</p>
{body}
</body>
</html>"""

    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(html)
