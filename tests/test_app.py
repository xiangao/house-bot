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
