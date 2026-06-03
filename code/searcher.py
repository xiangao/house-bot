import csv
import html as html_lib
import io
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

# curl_cffi impersonates a real browser's TLS/HTTP fingerprint. Redfin sits
# behind AWS WAF (CloudFront), which JA3/JA4-fingerprints the TLS ClientHello
# and 403s plain `requests` at the handshake — before any header is read.
# Header tweaks do nothing; the fingerprint is what must match a browser.
from curl_cffi import requests

GIS_CSV_URL = "https://www.redfin.com/stingray/api/gis-csv"

# Chrome version whose fingerprint curl_cffi clones. Bump if Redfin starts
# 403ing again (an old impersonation target eventually falls off WAF allowlists).
_IMPERSONATE = "chrome"

_HEADERS = {
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.redfin.com/",
}


@dataclass
class Listing:
    listing_id: str
    address: str
    price: float
    beds: float
    baths: float
    sqft: float
    url: str
    town: str
    property_type: str
    days_on_market: int
    year_built: int | None
    # Populated post-search by enrich_remarks() + classifier.is_builder_owned().
    # Cached in data/listings.csv so each listing is fetched only once.
    remarks: str = ""
    builder_owned: bool = False
    builder_match: str = ""


def _session() -> requests.Session:
    s = requests.Session(impersonate=_IMPERSONATE)
    s.headers.update(_HEADERS)
    return s



def search_town(
    session: requests.Session,
    town_cfg: dict,
    search_cfg: dict,
    region_id: str,
    region_type: str,
) -> list[Listing]:
    params = {
        "al": "1",
        "market": town_cfg["market"],
        "min_beds": search_cfg["min_beds"],
        "min_baths": search_cfg["min_baths"],
        "min_listing_price": search_cfg["min_price"],
        "max_listing_price": search_cfg["max_price"],
        "region_id": region_id,
        "region_type": region_type,
        "status": search_cfg.get("status", 1),
        "uipt": search_cfg.get("property_types", "1,2,3"),
        "v": "8",
        "sf": "1,2,3,5,6,7",  # include all listing types
        "num": "350",
    }
    resp = session.get(GIS_CSV_URL, params=params, timeout=30)
    resp.raise_for_status()

    # Redfin prepends a warning line before the CSV
    raw = resp.text
    lines = raw.splitlines()
    csv_start = next((i for i, l in enumerate(lines) if l.startswith("SALE TYPE")), None)
    if csv_start is None:
        return []

    min_price = float(search_cfg.get("min_price", 0))
    max_price = float(search_cfg.get("max_price", 1e9))
    min_beds = float(search_cfg.get("min_beds", 0))
    min_baths = float(search_cfg.get("min_baths", 0))
    min_year = search_cfg.get("min_year_built")

    reader = csv.DictReader(io.StringIO("\n".join(lines[csv_start:])))
    listings = []
    for row in reader:
        try:
            listing = _parse_row(row, town_cfg["name"])
            if not listing:
                continue
            if not (min_price <= listing.price <= max_price):
                continue
            if listing.beds < min_beds or listing.baths < min_baths:
                continue
            # Keep if built >= min_year, or if year unknown (may be renovated)
            if min_year and listing.year_built and listing.year_built < min_year:
                continue
            listings.append(listing)
        except (ValueError, KeyError):
            continue
    return listings


_URL_COL = "URL (SEE https://www.redfin.com/buy-a-home/comparative-market-analysis FOR INFO ON PRICING)"


def _parse_row(row: dict, town: str) -> Listing | None:
    # Skip MLS disclaimer row
    if "MLS rules" in (row.get("SALE TYPE") or ""):
        return None

    listing_id = (row.get("MLS#") or "").strip()
    if not listing_id:
        return None

    price_str = (row.get("PRICE") or "").replace("$", "").replace(",", "").strip()
    if not price_str:
        return None
    price = float(price_str)

    beds_str = row.get("BEDS") or "0"
    baths_str = row.get("BATHS") or "0"
    sqft_str = (row.get("SQUARE FEET") or "0").replace(",", "")
    dom_str = row.get("DAYS ON MARKET") or "0"
    yr_str = (row.get("YEAR BUILT") or "").strip()
    year_built = int(yr_str) if yr_str.isdigit() else None

    url_path = row.get(_URL_COL) or ""
    url = f"https://www.redfin.com{url_path}" if url_path.startswith("/") else url_path

    address_parts = [
        row.get("ADDRESS", ""),
        row.get("CITY", ""),
        row.get("STATE OR PROVINCE", ""),
        row.get("ZIP OR POSTAL CODE", ""),
    ]
    address = ", ".join(p for p in address_parts if p)

    return Listing(
        listing_id=listing_id,
        address=address,
        price=price,
        beds=float(beds_str),
        baths=float(baths_str),
        sqft=float(sqft_str) if sqft_str else 0.0,
        url=url,
        town=town,
        property_type=row.get("PROPERTY TYPE", ""),
        days_on_market=int(float(dom_str)) if dom_str else 0,
        year_built=year_built,
    )


# Marketing remarks are embedded in the listing HTML page inside a div whose
# `id` attribute is exactly `marketing-remarks-scroll`. The `belowTheFold`
# JSON API returns 403 behind WAF even with curl_cffi Chrome impersonation,
# but the public listing HTML still serves 200 — so we extract from there.
_REMARKS_DIV_RE = re.compile(
    r'id="marketing-remarks-scroll"[^>]*>(.*?)</div>',
    re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def fetch_remarks(session: requests.Session, url: str) -> str:
    """Fetch listing HTML and return the marketing remarks as plain text.

    Returns "" on any failure (404, 403, missing div, network error). The
    caller treats empty remarks as "not yet classifiable" and the classifier
    short-circuits to False.
    """
    try:
        resp = session.get(url, timeout=20)
        if resp.status_code != 200:
            return ""
        m = _REMARKS_DIV_RE.search(resp.text)
        if not m:
            return ""
        text = _TAG_RE.sub(" ", m.group(1))
        text = html_lib.unescape(text)
        return _WHITESPACE_RE.sub(" ", text).strip()
    except Exception:
        return ""


def enrich_remarks(
    listings: list[Listing],
    known: dict[str, dict],
    sleep_between: float = 0.8,
) -> None:
    """Populate listing.remarks in-place, fetching only when not already cached.

    `known` is the dict loaded from data/listings.csv. If a listing's row in
    `known` already has non-empty `remarks`, we reuse it — one HTTP per
    listing, ever. New listings (or any row whose remarks fetch previously
    failed) get a fresh fetch.
    """
    to_fetch = [l for l in listings if not (known.get(l.listing_id, {}).get("remarks") or "").strip()]
    for l in listings:
        cached = (known.get(l.listing_id, {}).get("remarks") or "").strip()
        if cached:
            l.remarks = cached

    if not to_fetch:
        return

    session = _session()
    session.get("https://www.redfin.com/", timeout=15)
    time.sleep(sleep_between)

    for i, listing in enumerate(to_fetch):
        listing.remarks = fetch_remarks(session, listing.url)
        if i < len(to_fetch) - 1:
            time.sleep(sleep_between)


def search_all(config: dict) -> list[Listing]:
    session = _session()
    # Seed session cookies so Redfin doesn't block the GIS-CSV endpoint
    session.get("https://www.redfin.com/", timeout=15)
    time.sleep(1.0)

    search_cfg = config["search"]
    all_listings: list[Listing] = []

    for town_cfg in config["towns"]:
        print(f"  Searching {town_cfg['name']}...")
        try:
            listings = search_town(
                session, town_cfg, search_cfg,
                town_cfg["region_id"], town_cfg["region_type"],
            )
            print(f"    {len(listings)} listings found")
            all_listings.extend(listings)
        except Exception as e:
            print(f"  WARNING [{town_cfg['name']}]: {e}")
        time.sleep(1.0)

    return all_listings
