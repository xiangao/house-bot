import csv
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from code.searcher import Listing

CSV_FIELDS = [
    "listing_id", "address", "price", "beds", "baths", "sqft",
    "url", "town", "property_type", "days_on_market", "year_built",
    "first_seen", "last_seen", "last_price",
    "remarks", "builder_owned", "builder_match",
]


@dataclass
class PriceDrop:
    listing: Listing
    old_price: float
    drop_amount: float
    drop_pct: float


@dataclass
class AnalysisResult:
    new_listings: list[Listing]
    price_drops: list[PriceDrop]


def load_known(csv_path: Path) -> dict[str, dict]:
    if not csv_path.exists():
        return {}
    known = {}
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            known[row["listing_id"]] = row
    return known


def save_listings(csv_path: Path, listings: list[Listing], known: dict[str, dict]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    today = str(date.today())
    updated = dict(known)

    for listing in listings:
        lid = listing.listing_id
        if lid in updated:
            updated[lid]["last_seen"] = today
            updated[lid]["last_price"] = updated[lid]["price"]
            updated[lid]["price"] = str(listing.price)
            updated[lid]["days_on_market"] = str(listing.days_on_market)
            # Remarks are cached; only overwrite if we have a non-empty value
            # (so a transient fetch failure doesn't wipe a good cache).
            if listing.remarks:
                updated[lid]["remarks"] = listing.remarks
            # Builder classification re-runs every time, so always overwrite.
            updated[lid]["builder_owned"] = "1" if listing.builder_owned else ""
            updated[lid]["builder_match"] = listing.builder_match
        else:
            updated[lid] = {
                "listing_id": lid,
                "address": listing.address,
                "price": str(listing.price),
                "beds": str(listing.beds),
                "baths": str(listing.baths),
                "sqft": str(listing.sqft),
                "url": listing.url,
                "town": listing.town,
                "property_type": listing.property_type,
                "days_on_market": str(listing.days_on_market),
                "year_built": str(listing.year_built) if listing.year_built else "",
                "first_seen": today,
                "last_seen": today,
                "last_price": str(listing.price),
                "remarks": listing.remarks,
                "builder_owned": "1" if listing.builder_owned else "",
                "builder_match": listing.builder_match,
            }

    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(updated.values())


def analyze(listings: list[Listing], known: dict[str, dict]) -> AnalysisResult:
    new_listings = []
    price_drops = []

    for listing in listings:
        lid = listing.listing_id
        if lid not in known:
            new_listings.append(listing)
        else:
            old_price = float(known[lid]["price"])
            if listing.price < old_price:
                drop = old_price - listing.price
                price_drops.append(PriceDrop(
                    listing=listing,
                    old_price=old_price,
                    drop_amount=drop,
                    drop_pct=drop / old_price,
                ))

    return AnalysisResult(new_listings=new_listings, price_drops=price_drops)
