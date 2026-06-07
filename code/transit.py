"""Driving distance from each listing to the nearest MBTA commuter rail station.

Two-stage to keep routing calls cheap:
  1. Haversine (free, instant) ranks the ~140 vendored stations and keeps the
     `CANDIDATE_K` nearest as-the-crow-flies.
  2. OSRM (public demo, no key) computes the actual *driving* distance to only
     those candidates; we keep the minimum.

Results are cached per listing in data/listings.csv (see analyzer.CSV_FIELDS),
so each listing costs at most CANDIDATE_K OSRM calls exactly once, ever —
mirroring the remarks-enrichment pattern in searcher.py.
"""
import json
import math
import time
from pathlib import Path

import requests

from code.searcher import Listing

_STATIONS_PATH = Path(__file__).parent / "mbta_commuter_rail_stations.json"
OSRM_URL = "https://router.project-osrm.org/route/v1/driving"

# How many straight-line-nearest stations to actually road-route to. The
# nearest-by-road station is almost always among the few nearest-by-line ones.
CANDIDATE_K = 4
_METERS_PER_MILE = 1609.344


def _load_stations() -> list[dict]:
    with open(_STATIONS_PATH) as f:
        return json.load(f)


_STATIONS = _load_stations()


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in miles (used only to pre-rank candidates)."""
    r = 3958.7613  # Earth radius, miles
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _osrm_drive(lat1: float, lon1: float, lat2: float, lon2: float,
                session: requests.Session) -> tuple[float, float] | None:
    """Return (miles, minutes) by car between two points, or None on failure.

    OSRM expects coordinates as lon,lat. We ask for no geometry (overview=false)
    since we only need the scalar distance/duration.
    """
    url = f"{OSRM_URL}/{lon1},{lat1};{lon2},{lat2}"
    try:
        resp = session.get(url, params={"overview": "false"}, timeout=20)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if data.get("code") != "Ok" or not data.get("routes"):
            return None
        route = data["routes"][0]
        return route["distance"] / _METERS_PER_MILE, route["duration"] / 60.0
    except Exception:
        return None


def nearest_station_by_car(
    lat: float, lon: float, session: requests.Session,
    sleep_between: float = 0.3,
) -> dict | None:
    """Nearest commuter rail station *by driving distance*.

    Pre-ranks all stations by straight-line distance, road-routes to the
    `CANDIDATE_K` nearest, and returns the one with the smallest driving
    distance: {"station", "miles", "minutes"}. Returns None if every routing
    call fails (the caller then leaves the listing's transit fields blank and
    retries it on a later run).
    """
    by_line = sorted(_STATIONS, key=lambda s: haversine_miles(lat, lon, s["lat"], s["lon"]))
    candidates = by_line[:CANDIDATE_K]

    best: dict | None = None
    for i, st in enumerate(candidates):
        drive = _osrm_drive(lat, lon, st["lat"], st["lon"], session)
        if drive is not None:
            miles, minutes = drive
            if best is None or miles < best["miles"]:
                best = {"station": st["name"], "miles": miles, "minutes": minutes}
        if i < len(candidates) - 1:
            time.sleep(sleep_between)
    return best


def enrich_transit(
    listings: list[Listing],
    known: dict[str, dict],
    sleep_between: float = 0.3,
) -> None:
    """Populate each listing's nearest-station fields in place, cache-aware.

    A listing is routed only if it lacks valid coordinates' cached result in
    `known` (i.e. no cached `station_miles`). Already-known listings reuse the
    cached station/miles/minutes, so each listing is routed at most once ever.
    """
    def _cached_miles(lid: str) -> str:
        return (known.get(lid, {}).get("station_miles") or "").strip()

    to_route = []
    for l in listings:
        cached = _cached_miles(l.listing_id)
        if cached:
            row = known[l.listing_id]
            l.nearest_station = row.get("nearest_station", "")
            l.station_miles = float(cached)
            mins = (row.get("station_minutes") or "").strip()
            l.station_minutes = float(mins) if mins else None
        elif l.latitude is not None and l.longitude is not None:
            to_route.append(l)

    if not to_route:
        return

    session = requests.Session()
    session.headers.update({"User-Agent": "house-bot/1.0 (personal listing monitor)"})
    for i, l in enumerate(to_route):
        result = nearest_station_by_car(l.latitude, l.longitude, session, sleep_between)
        if result is not None:
            l.nearest_station = result["station"]
            l.station_miles = result["miles"]
            l.station_minutes = result["minutes"]
        if i < len(to_route) - 1:
            time.sleep(sleep_between)
