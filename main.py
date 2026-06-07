import shutil
import subprocess
from pathlib import Path

import yaml
from dotenv import load_dotenv

from code.analyzer import analyze, load_known, save_listings
from code.classifier import is_builder_owned
from code.html_writer import write_html
from code.notifier import send_notification, write_summary
from code.searcher import enrich_remarks, search_all
from code.transit import enrich_transit

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

CONFIG_PATH = BASE_DIR / "config" / "searches.yaml"
LISTINGS_CSV = BASE_DIR / "data" / "listings.csv"
OUTPUT_PATH = BASE_DIR / "output" / "latest.txt"


def main() -> None:
    with open(CONFIG_PATH) as f:
        config = yaml.safe_load(f)

    tax_rates: dict[str, float] = {
        t["name"]: float(t.get("tax_rate_per_1000") or 0)
        for t in config.get("towns", [])
    }

    print("Searching Redfin...")
    listings = search_all(config)
    print(f"Total: {len(listings)} listings across all towns")

    known = load_known(LISTINGS_CSV)

    # Enrich each listing with its MLS marketing remarks (cached in CSV; each
    # listing is fetched at most once across all runs). Then classify whether
    # the home reads as a builder's personal residence — re-run every time so
    # editing the classifier reclassifies the whole CSV next run.
    enrich_remarks(listings, known)
    for listing in listings:
        flagged, match = is_builder_owned(listing.remarks, listing.year_built)
        listing.builder_owned = flagged
        listing.builder_match = match
    builder_count = sum(1 for l in listings if l.builder_owned)
    if builder_count:
        print(f"Builder-owned flagged: {builder_count}")

    # Driving distance to the nearest MBTA commuter rail station (OSRM, cached
    # per listing in the CSV; only new listings are routed).
    enrich_transit(listings, known)
    routed = sum(1 for l in listings if l.station_miles is not None)
    print(f"Transit distances: {routed}/{len(listings)} have a nearest-station drive")

    result = analyze(listings, known)

    print(f"New: {len(result.new_listings)}  Price drops: {len(result.price_drops)}")

    save_listings(LISTINGS_CSV, listings, known)
    write_summary(OUTPUT_PATH, result, tax_rates)

    html_path = BASE_DIR / "output" / "listings.html"
    search_cfg = config.get("search", {})
    write_html(
        LISTINGS_CSV, html_path, tax_rates,
        min_price=search_cfg.get("min_price"),
        max_price=search_cfg.get("max_price"),
    )
    print(f"Listings: {html_path}")

    send_notification(result)
    _deploy(html_path)


def _deploy(html_path: Path) -> None:
    site_dir = BASE_DIR / "site"
    if not site_dir.exists():
        print("  WARNING: site/ dir missing — skipping deploy")
        return
    shutil.copy(html_path, site_dir / "index.html")
    try:
        subprocess.run(["git", "add", "index.html"], cwd=site_dir, check=True)
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"], cwd=site_dir
        )
        if result.returncode == 0:
            print("  Site unchanged — skipping push")
            return
        subprocess.run(
            ["git", "commit", "-m", f"Update listings"],
            cwd=site_dir, check=True, capture_output=True,
        )
        subprocess.run(["git", "push", "-u", "origin", "gh-pages"], cwd=site_dir, check=True, capture_output=True)
        print("  Site deployed to GitHub Pages")
    except subprocess.CalledProcessError as e:
        print(f"  WARNING: deploy failed: {e}")


if __name__ == "__main__":
    main()
