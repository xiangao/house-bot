import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from code.analyzer import AnalysisResult, PriceDrop
from code.searcher import Listing


def _annual_tax(listing: Listing, tax_rates: dict[str, float]) -> float:
    rate = tax_rates.get(listing.town, 0.0)
    return listing.price * rate / 1000.0


def _transit_line(listing: Listing) -> str:
    if listing.station_miles is None or not listing.nearest_station:
        return ""
    mins = f", {listing.station_minutes:.0f} min" if listing.station_minutes is not None else ""
    return f"  {listing.station_miles:.1f} mi by car to {listing.nearest_station}{mins}\n"


def _fmt_listing(listing: Listing, tax_rates: dict[str, float]) -> str:
    sqft = f"  {listing.sqft:,.0f} sqft" if listing.sqft else ""
    dom = f"  {listing.days_on_market}d on market" if listing.days_on_market else ""
    tax = _annual_tax(listing, tax_rates)
    tax_line = f"  est. tax/yr: ${tax:,.0f}\n" if tax > 0 else ""
    return (
        f"  ${listing.price:,.0f}  —  {listing.beds:.0f}bd/{listing.baths:.1f}ba{sqft}{dom}\n"
        f"  {listing.address}\n"
        f"{tax_line}"
        f"{_transit_line(listing)}"
        f"  {listing.url}\n"
    )


def _fmt_price_drop(drop: PriceDrop, tax_rates: dict[str, float]) -> str:
    listing = drop.listing
    sqft = f"  {listing.sqft:,.0f} sqft" if listing.sqft else ""
    tax = _annual_tax(listing, tax_rates)
    tax_line = f"  est. tax/yr: ${tax:,.0f}\n" if tax > 0 else ""
    return (
        f"  ${listing.price:,.0f}  (was ${drop.old_price:,.0f},"
        f" -{drop.drop_pct * 100:.1f}%  save ${drop.drop_amount:,.0f})\n"
        f"  {listing.beds:.0f}bd/{listing.baths:.1f}ba{sqft}\n"
        f"  {listing.address}\n"
        f"{tax_line}"
        f"{_transit_line(listing)}"
        f"  {listing.url}\n"
    )


def build_email_body(result: AnalysisResult, tax_rates: dict[str, float] | None = None) -> str:
    tax_rates = tax_rates or {}
    lines = [f"House Search Report — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"]

    if result.new_listings:
        by_town: dict[str, list[Listing]] = {}
        for l in result.new_listings:
            by_town.setdefault(l.town, []).append(l)

        lines.append(f"NEW LISTINGS ({len(result.new_listings)} total)\n{'='*50}")
        for town, listings in sorted(by_town.items()):
            lines.append(f"\n{town} ({len(listings)})")
            lines.append("-" * len(town))
            for listing in sorted(listings, key=lambda l: l.days_on_market):
                lines.append(_fmt_listing(listing, tax_rates))
    else:
        lines.append("No new listings today.\n")

    if result.price_drops:
        lines.append(f"\nPRICE DROPS ({len(result.price_drops)} total)\n{'='*50}")
        for drop in sorted(result.price_drops, key=lambda d: -d.drop_pct):
            lines.append(f"\n{drop.listing.town}")
            lines.append(_fmt_price_drop(drop, tax_rates))

    return "\n".join(lines)


def write_summary(output_path: Path, result: AnalysisResult, tax_rates: dict[str, float] | None = None) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_email_body(result, tax_rates))


def send_notification(result: AnalysisResult) -> None:
    if not shutil.which("notify-send"):
        print("WARNING: notify-send not available — skipping desktop notification")
        return

    n_new = len(result.new_listings)
    n_drops = len(result.price_drops)
    if n_new == 0 and n_drops == 0:
        print("  Nothing to report — skipping notification")
        return

    title_parts = []
    if n_new:
        title_parts.append(f"{n_new} new listing{'s' if n_new > 1 else ''}")
    if n_drops:
        title_parts.append(f"{n_drops} price drop{'s' if n_drops > 1 else ''}")
    title = "House Bot: " + ", ".join(title_parts)

    lines = []
    for listing in sorted(result.new_listings, key=lambda l: l.price)[:5]:
        lines.append(f"${listing.price:,.0f}  {listing.beds:.0f}bd/{listing.baths:.1f}ba  {listing.town}")
    for drop in sorted(result.price_drops, key=lambda d: -d.drop_pct)[:3]:
        lines.append(
            f"${drop.listing.price:,.0f} (-{drop.drop_pct*100:.1f}%)  {drop.listing.town}"
        )

    body = "\n".join(lines)
    subprocess.run(["notify-send", title, body, "--urgency=normal"], check=False)
    print(f"  Notification sent: {title}")
