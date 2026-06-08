import csv
from pathlib import Path

from code.html_writer import render_page


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


def test_render_page_interactive_includes_controls_and_label(tmp_path: Path):
    csv_path = tmp_path / "listings.csv"
    _write_csv(csv_path, [_row()])
    html = render_page(
        csv_path, {"Natick, MA": 12.10}, 900000, 1500000,
        annotations={"73000001": {"status_label": "Favorite", "note": "n"}},
        interactive=True,
    )
    assert "annotate-status" in html       # interactive control rendered
    assert "label-favorite" in html         # annotation threaded to the card
