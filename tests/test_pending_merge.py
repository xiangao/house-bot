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
